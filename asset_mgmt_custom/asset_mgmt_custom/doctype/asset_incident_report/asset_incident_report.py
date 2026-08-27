import frappe
from frappe.model.document import Document


class AssetIncidentReport(Document):
    def on_submit(self):
        self.db_set("status", "Under Investigation")

    def on_cancel(self):
        self.db_set("status", "Closed")
