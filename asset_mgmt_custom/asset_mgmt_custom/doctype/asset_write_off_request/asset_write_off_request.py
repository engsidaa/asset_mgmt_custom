import frappe
from frappe.model.document import Document
from frappe.utils import today


class AssetWriteOffRequest(Document):
    def on_submit(self):
        self.db_set("status", "Pending Approval")

    def on_cancel(self):
        self.db_set("status", "Draft")
