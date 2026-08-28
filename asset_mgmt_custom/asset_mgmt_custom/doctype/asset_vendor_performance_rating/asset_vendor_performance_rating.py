import frappe
from frappe.model.document import Document


class AssetVendorPerformanceRating(Document):
    def before_save(self):
        scores = [
            self.response_time_score or 0,
            self.quality_score or 0,
            self.timeliness_score or 0,
            self.pricing_score or 0,
            self.communication_score or 0,
        ]
        filled = [s for s in scores if s]
        self.overall_score = round(sum(filled) / len(filled), 2) if filled else 0
