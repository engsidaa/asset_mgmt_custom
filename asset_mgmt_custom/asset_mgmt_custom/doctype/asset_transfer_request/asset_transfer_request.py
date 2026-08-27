import frappe
from frappe.model.document import Document


class AssetTransferRequest(Document):
    def validate(self):
        if self.from_branch and self.to_branch and self.from_branch == self.to_branch:
            frappe.throw("From Branch and To Branch cannot be the same.")

    def on_submit(self):
        self.db_set("status", "Pending")

    def on_cancel(self):
        self.db_set("status", "Pending")
