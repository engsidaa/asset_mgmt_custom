import frappe
from frappe.model.document import Document


class AssetLifeExtensionRequest(Document):
    def on_submit(self):
        self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Pending")
