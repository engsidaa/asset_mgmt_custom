import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class AssetSparePartRequest(Document):
    def validate(self):
        if (self.quantity_requested or 0) <= 0:
            frappe.throw("Quantity requested must be greater than zero.")

    def on_submit(self):
        self.db_set("status", "Approved")

    def on_cancel(self):
        self._cancel_stock_entry()
        self.db_set("status", "Cancelled")

    @frappe.whitelist()
    def issue_spare_part(self):
        """
        يُنشئ حركة مخزون حقيقية (Stock Entry من نوع Material Issue) تُخرِج
        الكمية المطلوبة فعلياً من مستودع قطعة الغيار — بدل الاكتفاء بتغيير
        حالة الحقل status فقط كما كان يحدث سابقاً (بدون أي أثر فعلي على
        المخزون). يُخفِّض أيضاً الكمية المتاحة على Asset Spare Part نفسها.
        """
        if self.status != "Approved":
            frappe.throw(_("يجب أن يكون الطلب بحالة 'Approved' قبل صرف القطعة."))

        if self.get("stock_entry") and frappe.db.exists("Stock Entry", self.stock_entry):
            frappe.throw(_("تم إنشاء حركة مخزون لهذا الطلب بالفعل: {0}").format(self.stock_entry))

        spare_part = frappe.get_doc("Asset Spare Part", self.spare_part)
        if not spare_part.item_code or not spare_part.warehouse:
            frappe.throw(
                _(
                    "لا يمكن إنشاء حركة مخزون: قطعة الغيار {0} غير مربوطة بصنف "
                    "(Item) أو مستودع (Warehouse) في ERPNext. اربطها أولاً من "
                    "شاشة Asset Spare Part."
                ).format(spare_part.name)
            )

        qty = flt(self.quantity_requested)
        if spare_part.quantity and qty > flt(spare_part.quantity):
            frappe.throw(
                _("الكمية المطلوبة ({0}) أكبر من الكمية المتاحة فعلياً ({1}) لقطعة الغيار {2}.").format(
                    qty, spare_part.quantity, spare_part.name
                )
            )

        asset = frappe.get_doc("Asset", self.asset)
        company = asset.company or frappe.defaults.get_user_default("Company")

        branch = asset.get("custom_branch")
        cost_center = (
            (branch and frappe.db.get_value("Branch", branch, "custom_cost_center"))
            or asset.get("cost_center")
        )

        expense_account = None
        if asset.asset_category:
            expense_account = frappe.db.get_value(
                "Asset Category Account",
                {"parent": asset.asset_category, "company_name": company},
                "custom_maintenance_expense_account",
            )

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.company = company
        se.posting_date = today()
        se.remarks = _("Spare part issued for Asset {0} via {1}").format(asset.asset_name, self.name)

        item_row = {
            "item_code": spare_part.item_code,
            "qty": qty,
            "s_warehouse": spare_part.warehouse,
        }
        if cost_center:
            item_row["cost_center"] = cost_center
        if expense_account:
            item_row["expense_account"] = expense_account
        se.append("items", item_row)

        se.insert(ignore_permissions=True)
        se.submit()

        frappe.db.set_value(
            "Asset Spare Part", spare_part.name, "quantity", flt(spare_part.quantity) - qty
        )

        self.db_set("stock_entry", se.name)
        self.db_set("quantity_issued", qty)
        self.db_set("status", "Issued")

        frappe.msgprint(
            _("تم إنشاء حركة المخزون: <a href='/app/stock-entry/{0}'>{0}</a>").format(se.name),
            alert=True, indicator="green"
        )
        return se.name

    def _cancel_stock_entry(self):
        """
        لو كانت القطعة صُرفت بالفعل (فيه Stock Entry مُسلَّم)، نُلغيه ونعيد
        الكمية إلى Asset Spare Part — باستخدام quantity_issued المُسجَّلة
        على هذا المستند نفسه (وليس بمطابقة الصنف عكسياً من بنود الحركة، لأن
        أكثر من Asset Spare Part قد يتشاركوا نفس الصنف/الـ Item).
        """
        se_name = self.get("stock_entry")
        if not se_name or not frappe.db.exists("Stock Entry", se_name):
            return
        se = frappe.get_doc("Stock Entry", se_name)
        if se.docstatus == 1:
            se.cancel()

        qty_to_restore = flt(self.get("quantity_issued"))
        if qty_to_restore and self.spare_part:
            current_qty = flt(frappe.db.get_value("Asset Spare Part", self.spare_part, "quantity"))
            frappe.db.set_value(
                "Asset Spare Part", self.spare_part, "quantity", current_qty + qty_to_restore
            )
