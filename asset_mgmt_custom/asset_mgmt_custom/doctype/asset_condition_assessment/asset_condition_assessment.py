import frappe
from frappe import _
from frappe.model.document import Document


_RATING_SCORE = {"Excellent": 10, "Good": 8, "Fair": 5, "Poor": 3, "Critical": 1}


class AssetConditionAssessment(Document):
    def validate(self):
        if not self.condition_score and self.condition_rating:
            self.condition_score = _RATING_SCORE.get(self.condition_rating, 5)

    def after_insert(self):
        # Write the latest condition back to the asset custom field
        frappe.db.set_value("Asset", self.asset, "custom_asset_condition", self.condition_rating)
