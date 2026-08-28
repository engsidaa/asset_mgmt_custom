import frappe
from frappe.model.document import Document

class AssetWorkOrder(Document):
    def on_submit(self):
        self.db_set("status", "قيد التنفيذ")

    def on_cancel(self):
        self.db_set("status", "ملغي")
