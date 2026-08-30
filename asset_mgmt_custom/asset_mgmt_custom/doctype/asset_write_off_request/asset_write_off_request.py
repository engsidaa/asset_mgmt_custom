import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt


class AssetWriteoffRequest(Document):
    def on_submit(self):
        self.db_set("status", "Pending Approval")

    def on_cancel(self):
        self.db_set("status", "Draft")

    @frappe.whitelist()
    def create_journal_entry(self):
        """Create a Journal Entry for the write-off loss after approval."""
        if self.status not in ("Approved",):
            frappe.throw(_("يجب أن يكون الطلب بحالة 'موافق' قبل إنشاء القيد المحاسبي."))

        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            frappe.throw(_(f"القيد المحاسبي {self.journal_entry} موجود بالفعل."))

        asset = frappe.get_doc("Asset", self.asset)
        company = asset.company or frappe.defaults.get_user_default("Company")

        # estimated_loss_value هو الحقل الحقيقي في هذا المستند (اللي المستخدم
        # بيملاه فعلياً من الشاشة) — نسخة سابقة من هذا الكود كانت بتقرأ
        # book_value/amount بدل منه، وهما حقلان غير موجودين إطلاقاً في هذا
        # الـ DocType، فكانت القيمة المُدخَلة من المستخدم بتتجاهَل بالكامل
        # وبيُحتسَب مبلغ تلقائي من جدول الإهلاك دايماً بدلها.
        book_value = flt(self.get("estimated_loss_value"))

        if not book_value:
            # لا توجد قيمة خسارة مُقدَّرة مُدخَلة يدوياً — نحسبها من قيمة
            # الأصل بعد الإهلاك
            book_value = flt(asset.get("gross_purchase_amount", 0)) - flt(
                frappe.db.sql("""
                    SELECT COALESCE(SUM(depreciation_amount), 0)
                    FROM `tabDepreciation Schedule`
                    WHERE parent = %s AND docstatus = 1
                """, self.asset)[0][0]
            )

        if not book_value:
            frappe.throw(_("لا يمكن تحديد القيمة الدفترية للأصل. يرجى تحديد المبلغ يدوياً."))

        # Get fixed asset account from asset category
        asset_account = frappe.db.sql("""
            SELECT fixed_asset_account
            FROM `tabAsset Category Account`
            WHERE parent = %s AND company_name = %s
            LIMIT 1
        """, (asset.asset_category, company), as_dict=True)
        asset_account = asset_account[0]["fixed_asset_account"] if asset_account else None

        if not asset_account:
            frappe.throw(_(
                "لا يوجد حساب أصول ثابتة مرتبط بفئة الأصل. "
                "تأكد من إعداد Asset Category Accounts للشركة."
            ))

        # Write-off expense account
        # disposal_account ("Gain/Loss Account on Asset Disposal") هو الحقل
        # الحقيقي والمخصص لهذا الغرض تحديداً في Company. النسخة السابقة
        # كانت بتستخدم write_off_account كأولوية أولى، وبتحاول كـ fallback
        # قراءة حقل "loss_on_disposal_of_assets" غير موجود إطلاقاً في
        # ERPNext — كان هيتسبب في خطأ SQL خام ("Unknown column") لو
        # write_off_account فاضي، بدل رسالة واضحة.
        writeoff_account = (
            frappe.db.get_value("Company", company, "disposal_account")
            or frappe.db.get_value("Company", company, "write_off_account")
        )
        if not writeoff_account:
            frappe.throw(_(
                "لا يوجد حساب شطب مُعيَّن في إعدادات الشركة. "
                "حدد 'Write Off Account' في إعدادات الشركة."
            ))

        # مركز التكلفة إلزامي في ERPNext لأي حساب أرباح وخسائر (زي حساب
        # الشطب هنا) — لو الحقل فاضي على المستند، نرجع لمركز تكلفة الأصل
        # نفسه بدل ما نسيب القيد يفشل بدون مركز تكلفة.
        cost_center = self.cost_center or asset.get("cost_center")

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Write Off Entry"
        je.posting_date = today()
        je.company = company
        je.user_remark = f"شطب الأصل: {asset.asset_name} — {self.name}"
        if cost_center:
            je.cost_center = cost_center

        # Debit: Write-off expense (loss)
        # ملاحظة: reference_type لازم يكون واحداً من القيم المسموحة في
        # Journal Entry Account (Sales/Purchase Invoice، Asset، إلخ) —
        # "Asset Write Off Request" (self.doctype) مش من ضمنها، وكانت
        # بتُفشل هذا القيد دايماً. نرجع للأصل نفسه كمرجع بدلاً منه.
        je.append("accounts", {
            "account": writeoff_account,
            "debit_in_account_currency": book_value,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })

        # Credit: Fixed asset account
        je.append("accounts", {
            "account": asset_account,
            "credit_in_account_currency": book_value,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("journal_entry", je.name)
        self.db_set("status", "Executed")

        frappe.msgprint(
            f"تم إنشاء قيد اليومية: <a href='/app/journal-entry/{je.name}'>{je.name}</a>",
            alert=True, indicator="green"
        )
        return je.name
