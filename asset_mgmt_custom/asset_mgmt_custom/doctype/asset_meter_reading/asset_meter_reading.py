import frappe
from frappe.model.document import Document

class AssetMeterReading(Document):
    def before_save(self):
        # Get previous reading for this asset and meter type
        prev = frappe.db.sql("""
            SELECT current_reading FROM `tabAsset Meter Reading`
            WHERE asset = %s AND meter_type = %s AND name != %s
            ORDER BY reading_date DESC, creation DESC LIMIT 1
        """, (self.asset, self.meter_type, self.name or ""))
        self.previous_reading = prev[0][0] if prev else 0
        consumed = (self.current_reading or 0) - (self.previous_reading or 0)
        self.units_consumed = max(consumed, 0)
