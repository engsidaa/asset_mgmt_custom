import frappe
from frappe.model.document import Document

class AssetRiskAssessment(Document):
    def before_save(self):
        for item in self.risk_items:
            item.risk_score = (item.likelihood or 0) * (item.severity or 0)
