import frappe
from frappe.model.document import Document

from asset_mgmt_custom.esg import (
    check_anomaly,
    create_early_inspection_alert,
    get_electricity_emission_factor,
)


class AssetEnergyLog(Document):
    def validate(self):
        if self.reading_start is not None and self.reading_end is not None:
            units = max(0, (self.reading_end or 0) - (self.reading_start or 0))
            self.units_consumed = units
            self.total_cost = units * (self.unit_rate or 0)
        self.co2e_kg = (self.units_consumed or 0) * get_electricity_emission_factor()

    def on_update(self):
        self._detect_anomaly()

    def _detect_anomaly(self):
        if self.get("anomaly_work_order"):
            return
        is_anomaly, baseline = check_anomaly(
            "Asset Energy Log", self.asset, self.units_consumed, self.name, "units_consumed"
        )
        if not is_anomaly:
            return

        self.db_set("is_anomaly", 1, update_modified=False)
        wo_name = create_early_inspection_alert(
            "Asset Energy Log", self.name, self.asset, self.units_consumed, baseline, "kWh"
        )
        if wo_name:
            self.db_set("anomaly_work_order", wo_name, update_modified=False)
