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
