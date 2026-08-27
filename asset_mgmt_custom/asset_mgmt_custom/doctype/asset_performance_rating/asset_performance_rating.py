import frappe
from frappe.model.document import Document


class AssetPerformanceRating(Document):
    def validate(self):
        for field in ["performance_score", "reliability_score", "efficiency_score"]:
            val = self.get(field)
            if val is not None and (val < 1 or val > 10):
                frappe.throw(f"{field.replace('_', ' ').title()} must be between 1 and 10.")
