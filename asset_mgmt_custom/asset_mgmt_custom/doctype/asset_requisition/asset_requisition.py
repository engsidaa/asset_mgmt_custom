import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class AssetRequisition(Document):
    def validate(self):
        self._check_spare_availability()

    def _check_spare_availability(self):
        if not self.asset_category:
            return
        filters = {
            "asset_category": self.asset_category,
            "custom_is_spare": 1,
            "docstatus": 1,
        }
        if self.item_code:
            filters["item_code"] = self.item_code
        spare = frappe.db.get_value("Asset", filters, "name")
        if spare:
            self.spare_available = 1
            self.spare_asset = spare
        else:
            self.spare_available = 0
            self.spare_asset = None

    @frappe.whitelist()
    def create_asset_movement(self):
        """Convert approved AR with spare to Asset Movement (Transfer)."""
        if not self.spare_asset:
            frappe.throw(_("No spare asset linked to create a movement"))
        if self.status != "Approved":
            frappe.throw(_("Requisition must be Approved before creating a movement"))
        doc = frappe.new_doc("Asset Movement")
        doc.purpose = "Transfer"
        doc.company = frappe.defaults.get_user_default("Company")
        doc.transaction_date = today()
        doc.append("assets", {"asset": self.spare_asset})
        doc.insert(ignore_permissions=True)
        self.db_set("status", "Fulfilled")
        return doc.name

    @frappe.whitelist()
    def create_purchase_requisition(self):
        """Create a Material Request (Purchase) from this requisition when no spare is available."""
        if self.spare_available:
            frappe.throw(_("A spare asset is available. Use 'Create Asset Movement' instead."))
        if self.status != "Approved":
            frappe.throw(_("Requisition must be Approved before creating a purchase request."))

        mr = frappe.new_doc("Material Request")
        mr.material_request_type = "Purchase"
        mr.transaction_date = frappe.utils.today()
        mr.schedule_date = self.required_by or frappe.utils.add_days(frappe.utils.today(), 30)
        mr.custom_source_asset_requisition = self.name if frappe.db.exists("Custom Field",
            "Material Request-custom_source_asset_requisition") else None

        if self.item_code:
            mr.append("items", {
                "item_code": self.item_code,
                "qty": self.quantity or 1,
                "schedule_date": mr.schedule_date,
            })
        else:
            frappe.throw(_("Please set Item Code on the requisition before creating a purchase request."))

        mr.insert(ignore_permissions=True)
        self.db_set("material_request", mr.name)
        self.db_set("status", "Fulfilled")
        frappe.msgprint(
            f"تم إنشاء طلب الشراء: <a href='/app/material-request/{mr.name}'>{mr.name}</a>",
            alert=True, indicator="green"
        )
        return mr.name
