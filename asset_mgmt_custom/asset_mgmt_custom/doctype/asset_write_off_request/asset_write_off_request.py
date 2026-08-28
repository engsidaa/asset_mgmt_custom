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
        book_value = flt(getattr(self, "book_value", None) or getattr(self, "amount", None) or 0)

        if not book_value:
            # Try to compute from asset's value after depreciation
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
        writeoff_account = (
            frappe.db.get_value("Company", company, "write_off_account")
            or frappe.db.get_value("Company", company, "loss_on_disposal_of_assets")
        )
        if not writeoff_account:
            frappe.throw(_(
                "لا يوجد حساب شطب مُعيَّن في إعدادات الشركة. "
                "حدد 'Write Off Account' في إعدادات الشركة."
            ))

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Write Off Entry"
        je.posting_date = today()
        je.company = company
        je.user_remark = f"شطب الأصل: {asset.asset_name} — {self.name}"
        if self.cost_center:
            je.cost_center = self.cost_center

        # Debit: Write-off expense (loss)
        je.append("accounts", {
            "account": writeoff_account,
            "debit_in_account_currency": book_value,
            "cost_center": self.cost_center or None,
            "reference_type": self.doctype,
            "reference_name": self.name,
        })

        # Credit: Fixed asset account
        je.append("accounts", {
            "account": asset_account,
            "credit_in_account_currency": book_value,
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
