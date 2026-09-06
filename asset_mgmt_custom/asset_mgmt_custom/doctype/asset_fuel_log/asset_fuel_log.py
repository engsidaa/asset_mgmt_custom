import frappe
from frappe.model.document import Document

from asset_mgmt_custom.esg import (
	check_anomaly,
	create_early_inspection_alert,
	get_fuel_emission_factor,
)


class AssetFuelLog(Document):
	def validate(self):
		self.km_driven = max(0, (self.closing_meter or 0) - (self.opening_meter or 0))
		self.total_cost = (self.liters_filled or 0) * (self.unit_cost or 0)
		self.co2e_kg = (self.liters_filled or 0) * get_fuel_emission_factor(self.fuel_type)

	def on_update(self):
		self._detect_anomaly()

	def _detect_anomaly(self):
		if self.get("anomaly_work_order"):
			return
		is_anomaly, baseline = check_anomaly(
			"Asset Fuel Log", self.asset, self.liters_filled, self.name, "liters_filled"
		)
		if not is_anomaly:
			return

		self.db_set("is_anomaly", 1, update_modified=False)
		wo_name = create_early_inspection_alert(
			"Asset Fuel Log", self.name, self.asset, self.liters_filled, baseline, "liters"
		)
		if wo_name:
			self.db_set("anomaly_work_order", wo_name, update_modified=False)
