import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import getdate, today


class AssetLease(Document):
    def validate(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            frappe.throw(_("Lease End Date must be after Start Date."))

    def on_submit(self):
        self.db_set("status", "Active")

    def on_cancel(self):
        self.db_set("status", "Terminated")
