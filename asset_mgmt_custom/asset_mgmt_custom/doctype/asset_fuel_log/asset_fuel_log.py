import frappe
from frappe.model.document import Document


class AssetFuelLog(Document):
	def validate(self):
		self.km_driven = max(0, (self.closing_meter or 0) - (self.opening_meter or 0))
		self.total_cost = (self.liters_filled or 0) * (self.unit_cost or 0)
