import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class AssetVendorContract(Document):
    def validate(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw("End Date must be after Start Date.")

    def on_submit(self):
        self.db_set("status", "Active")

    def on_cancel(self):
        self.db_set("status", "Cancelled")
