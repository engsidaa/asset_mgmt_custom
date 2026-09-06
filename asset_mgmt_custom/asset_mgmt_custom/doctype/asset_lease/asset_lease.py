"""
Asset Lease
-----------
لا يوجد أي دعم أصلي (Core) لمحاسبة الإيجار وفق IFRS 16 في ERPNext — هذا
المستند يغطي حالتين مختلفتين تماماً محاسبياً، مُميَّزتين بحقل
lease_direction:

  - "We are the Lessor" (الوضع الافتراضي، السلوك القديم دون أي تغيير):
    الشركة تُؤجِّر أصلاً تملكه بالفعل (asset) لطرف آخر (branch داخلي أو
    طرف خارجي). لا رسملة IFRS 16 هنا — مجرد تتبع عقد وإيراد إيجار.

  - "We are the Lessee": الشركة تستأجر معدة لا تملكها (سيارة توصيل،
    ماكينة نقاط بيع، معدات مطبخ...). هنا فقط تنطبق محاسبة IFRS 16:
    عند التسليم، تُحسَب القيمة الحالية (Present Value) لإجمالي دفعات
    الإيجار المتبقية بمعدل الخصم المحدد، وتُرسمَل كـ "أصل حق استخدام"
    (Right-of-Use Asset) مقابل "التزام إيجار" (Lease Liability) بنفس
    القيمة. شهرياً، يُقسَّم القسط إلى فائدة (تُحسَب من رصيد الالتزام
    المتبقي) وأصل الالتزام (الباقي)، ويُهلَك أصل حق الاستخدام بالقسط
    الثابت على مدى مدة العقد — بقيود يومية منفصلة تماماً عن أي محاسبة
    إهلاك لأصول ERPNext القياسية (لأن أصل حق الاستخدام هنا ليس بالضرورة
    "Asset" مُسجَّلاً في ERPNext، بل حسابات مخصصة على هذا المستند نفسه).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate, today


def _month_count(start_date, end_date):
    start_date, end_date = getdate(start_date), getdate(end_date)
    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


def _present_value_of_annuity(payment, monthly_rate, months):
    """القيمة الحالية لسلسلة دفعات متساوية (Ordinary Annuity — الدفعة في
    نهاية كل فترة)، وفق الصيغة المعيارية: PV = P * (1 - (1+r)^-n) / r.
    عند معدل خصم صفري (نادر لكن ممكن)، القيمة الحالية = مجموع الدفعات."""
    if monthly_rate == 0:
        return flt(payment) * months
    factor = (1 - (1 + monthly_rate) ** (-months)) / monthly_rate
    return flt(payment) * factor


def post_monthly_amortization(lease_name):
    """يُستدعى عبر frappe.enqueue من tasks.process_lease_amortization()."""
    frappe.get_doc("Asset Lease", lease_name)._post_monthly_amortization()


class AssetLease(Document):
    def validate(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            frappe.throw(_("Lease End Date must be after Start Date."))

    def on_submit(self):
        self.db_set("status", "Active")
        if self.lease_direction == "We are the Lessee":
            self._recognize_ifrs16_lease()

    def on_cancel(self):
        self.db_set("status", "Terminated")
        self._reverse_ifrs16_lease()

    # -----------------------------------------------------------------
    # IFRS 16 — الاعتراف الابتدائي (Initial Recognition)
    # -----------------------------------------------------------------

    def _recognize_ifrs16_lease(self):
        if self.get("initial_journal_entry"):
            return

        months = _month_count(self.start_date, self.end_date)
        if months <= 0:
            frappe.throw(_("Lease term must be at least one month for IFRS 16 recognition."))

        monthly_rate = flt(self.discount_rate) / 100 / 12
        rou_value = _present_value_of_annuity(flt(self.monthly_rent), monthly_rate, months)

        cost_center = self.cost_center
        ref = {"reference_type": "Asset Lease", "reference_name": self.name}

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.start_date
        je.company = self.company
        if cost_center:
            je.cost_center = cost_center
        je.user_remark = _("IFRS 16 initial recognition for lease {0} (Asset {1})").format(
            self.name, self.asset_name or self.asset
        )
        je.append("accounts", {
            "account": self.rou_asset_account,
            "debit_in_account_currency": rou_value,
            "cost_center": cost_center,
            **ref,
        })
        je.append("accounts", {
            "account": self.lease_liability_account,
            "credit_in_account_currency": rou_value,
            "cost_center": cost_center,
            **ref,
        })
        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("initial_rou_value", rou_value, update_modified=False)
        self.db_set("lease_liability_balance", rou_value, update_modified=False)
        self.db_set("initial_journal_entry", je.name, update_modified=False)
        self.db_set("next_amortization_date", add_months(self.start_date, 1), update_modified=False)

    def _reverse_ifrs16_lease(self):
        if self.get("initial_journal_entry") and frappe.db.exists("Journal Entry", self.initial_journal_entry):
            je = frappe.get_doc("Journal Entry", self.initial_journal_entry)
            if je.docstatus == 1:
                je.cancel()

        for row in self.get("lease_amortization_schedule") or []:
            if row.journal_entry and frappe.db.exists("Journal Entry", row.journal_entry):
                amort_je = frappe.get_doc("Journal Entry", row.journal_entry)
                if amort_je.docstatus == 1:
                    amort_je.cancel()

    # -----------------------------------------------------------------
    # IFRS 16 — الإطفاء الشهري (Monthly Amortization)
    # -----------------------------------------------------------------

    def _post_monthly_amortization(self):
        """
        طريقة الفائدة الفعلية (Effective Interest Method) المعيارية: فائدة
        الشهر = رصيد الالتزام المتبقي × المعدل الشهري، وأصل الالتزام
        المسدَّد = القسط الثابت - الفائدة. يُهلَك أصل حق الاستخدام بالتوازي
        بالقسط الثابت (Straight-Line) على كامل مدة العقد — منفصل تماماً
        عن جدول الفائدة/الالتزام، تماشياً مع IFRS 16 (الإهلاك لا علاقة له
        بمعدل الفائدة).
        """
        if self.docstatus != 1 or self.status != "Active":
            return
        if self.lease_direction != "We are the Lessee":
            return
        if not self.get("next_amortization_date") or getdate(self.next_amortization_date) > getdate(today()):
            return
        if flt(self.lease_liability_balance) <= 0:
            return

        monthly_rate = flt(self.discount_rate) / 100 / 12
        interest_amount = flt(self.lease_liability_balance) * monthly_rate
        payment = flt(self.monthly_rent)
        principal_amount = payment - interest_amount

        # آخر قسط: لا نُسدِّد أكثر من رصيد الالتزام المتبقي فعلياً (فروق
        # تقريب صغيرة عبر الشهور قد تترك رصيداً متبقياً أقل من قسط كامل).
        if principal_amount > flt(self.lease_liability_balance):
            principal_amount = flt(self.lease_liability_balance)
            payment = principal_amount + interest_amount

        months_total = _month_count(self.start_date, self.end_date)
        depreciation_amount = flt(self.initial_rou_value) / months_total if months_total else 0

        posting_date = self.next_amortization_date
        cost_center = self.cost_center
        ref = {"reference_type": "Asset Lease", "reference_name": self.name}

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = posting_date
        je.company = self.company
        if cost_center:
            je.cost_center = cost_center
        je.user_remark = _("IFRS 16 monthly lease amortization for {0}").format(self.name)

        je.append("accounts", {
            "account": self.lease_liability_account,
            "debit_in_account_currency": principal_amount,
            "cost_center": cost_center,
            **ref,
        })
        je.append("accounts", {
            "account": self.interest_expense_account,
            "debit_in_account_currency": interest_amount,
            "cost_center": cost_center,
            **ref,
        })
        je.append("accounts", {
            "account": self.lease_payable_account,
            "credit_in_account_currency": payment,
            "cost_center": cost_center,
            **ref,
        })
        if depreciation_amount:
            je.append("accounts", {
                "account": self.rou_depreciation_expense_account,
                "debit_in_account_currency": depreciation_amount,
                "cost_center": cost_center,
                **ref,
            })
            je.append("accounts", {
                "account": self.accumulated_rou_depreciation_account,
                "credit_in_account_currency": depreciation_amount,
                "cost_center": cost_center,
                **ref,
            })

        je.insert(ignore_permissions=True)
        je.submit()

        new_balance = flt(self.lease_liability_balance) - principal_amount
        self.append("lease_amortization_schedule", {
            "posting_date": posting_date,
            "payment_amount": payment,
            "interest_amount": interest_amount,
            "principal_amount": principal_amount,
            "closing_liability_balance": new_balance,
            "depreciation_amount": depreciation_amount,
            "journal_entry": je.name,
        })
        self.lease_liability_balance = new_balance
        self.next_amortization_date = add_months(posting_date, 1)
        self.save(ignore_permissions=True)
