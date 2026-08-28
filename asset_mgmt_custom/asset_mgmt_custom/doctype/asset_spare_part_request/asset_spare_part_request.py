import frappe
from frappe.model.document import Document


class AssetSparePartRequest(Document):
    def validate(self):
        if (self.quantity_requested or 0) <= 0:
            frappe.throw("Quantity requested must be greater than zero.")

    def on_submit(self):
        self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Cancelled")
