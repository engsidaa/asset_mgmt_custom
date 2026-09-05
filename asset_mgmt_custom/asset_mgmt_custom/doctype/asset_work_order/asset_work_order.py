import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, now_datetime, today

from asset_mgmt_custom.overrides.asset_repair import _update_asset_maintenance_summary


class AssetWorkOrder(Document):
    def before_insert(self):
        self._apply_sla_policy()

    def on_submit(self):
        self.db_set("status", "قيد التنفيذ")

    def on_update_after_submit(self):
        """
        الحالة (status) والحقول المرتبطة بالإتمام صارت allow_on_submit — أمر
        العمل بيتقدَّم بعد التسليم (Submit) من "قيد التنفيذ" إلى "مكتمل" عن
        طريق تعديل هذا الحقل على نفس المستند المُسلَّم، وليس عبر مستند جديد.
        عند وصوله لحالة "مكتمل" نرحِّل تكلفته الفعلية محاسبياً (مرة واحدة
        فقط) ونحدِّث إجمالي تكلفة الصيانة على الأصل.
        """
        if self.status == "مكتمل":
            self._post_maintenance_cost_gl_entry()
        _update_asset_maintenance_summary(self.asset)

    def on_cancel(self):
        self.db_set("status", "ملغي")
        self._cancel_maintenance_cost_gl_entry()
        _update_asset_maintenance_summary(self.asset)

    def _post_maintenance_cost_gl_entry(self):
        """
        قيد محاسبي تلقائي (Idempotent) لتكلفة أمر العمل عند إتمامه:
        من حـ/ مصروف الصيانة (custom_maintenance_expense_account على فئة
        الأصل) ← إلى حـ/ التزامات صيانة مستحقة
        (custom_maintenance_accrued_liability_account) — نفس نمط OpEx
        المُستخدَم فعلياً في Asset Repair، لأن أمر العمل هنا دائماً مصروف
        تشغيلي (لا يوجد له مفهوم رسملة/CapEx مثل الإصلاح).
        """
        if self.get("journal_entry"):
            return

        total_cost = flt(self.actual_cost) or (flt(self.labor_cost) + flt(self.spare_parts_cost))
        if not total_cost:
            return

        asset = frappe.get_doc("Asset", self.asset)
        company = asset.company or frappe.defaults.get_user_default("Company")

        category_account = frappe.db.get_value(
            "Asset Category Account",
            {"parent": asset.asset_category, "company_name": company},
            ["custom_maintenance_expense_account", "custom_maintenance_accrued_liability_account"],
            as_dict=True,
        )
        if not category_account or not category_account.custom_maintenance_expense_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Expense Account' on the Asset Category Account "
                    "for {0} / {1} before completing this work order."
                ).format(asset.asset_category, company),
                title=_("Missing Maintenance Expense Account"),
            )
        if not category_account.custom_maintenance_accrued_liability_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Accrued Liability Account' on the Asset Category "
                    "Account for {0} / {1} before completing this work order."
                ).format(asset.asset_category, company),
                title=_("Missing Accrued Liability Account"),
            )

        # مركز التكلفة: أولوية للحقل المُدخَل يدوياً على أمر العمل نفسه، وإلا
        # مركز تكلفة الفرع (custom_cost_center) المرتبط بأصل هذا الأمر، وإلا
        # مركز تكلفة الأصل نفسه — بدل ما يفشل القيد بدون مركز تكلفة.
        cost_center = (
            self.cost_center
            or (self.branch and frappe.db.get_value("Branch", self.branch, "custom_cost_center"))
            or asset.get("cost_center")
        )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.completion_date or today()
        je.company = company
        if cost_center:
            je.cost_center = cost_center
        je.user_remark = _("Maintenance work order cost for Asset {0} via {1}").format(
            asset.asset_name, self.name
        )

        je.append("accounts", {
            "account": category_account.custom_maintenance_expense_account,
            "debit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })
        je.append("accounts", {
            "account": category_account.custom_maintenance_accrued_liability_account,
            "credit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("journal_entry", je.name, update_modified=False)

    def _cancel_maintenance_cost_gl_entry(self):
        je_name = self.get("journal_entry")
        if not je_name or not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.cancel()

    def _apply_sla_policy(self):
        """
        تُحدَّد مواعيد الاستجابة/الحل المستحقة مرة واحدة عند الإنشاء بناءً
        على سياسة SLA المطابقة لأولوية أمر العمل، بدل الثوابت الثابتة
        (48 ساعة/3 أيام) التي كانت مكتوبة مباشرة في الكود سابقاً.
        """
        if not self.priority:
            return

        policy = frappe.db.get_value(
            "Asset Maintenance SLA Policy",
            self.priority,
            ["name", "response_hours", "resolution_hours"],
            as_dict=True,
        )
        if not policy:
            return

        base = now_datetime()
        self.sla_policy = policy.name
        self.response_due_by = add_to_date(base, hours=flt(policy.response_hours))
        self.resolution_due_by = add_to_date(base, hours=flt(policy.resolution_hours))
