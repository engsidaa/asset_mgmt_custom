import frappe
from frappe.model.document import Document

class AssetWorkPermit(Document):
    def on_submit(self):
        self.db_set("status", "صالح")

    def on_cancel(self):
        self.db_set("status", "ملغي")
