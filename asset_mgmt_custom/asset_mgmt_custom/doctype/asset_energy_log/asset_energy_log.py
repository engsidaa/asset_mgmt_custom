import frappe
from frappe.model.document import Document


class AssetEnergyLog(Document):
    def validate(self):
        if self.reading_start is not None and self.reading_end is not None:
            units = max(0, (self.reading_end or 0) - (self.reading_start or 0))
            self.units_consumed = units
            self.total_cost = units * (self.unit_rate or 0)
