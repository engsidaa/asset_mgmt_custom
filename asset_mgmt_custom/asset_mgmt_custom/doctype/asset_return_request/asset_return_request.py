import frappe
from frappe.model.document import Document
from frappe.utils import today


class AssetReturnRequest(Document):
    def on_submit(self):
        self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Pending")

    def mark_returned(self):
        self.db_set("status", "Returned")
        self.db_set("actual_return_date", today())
