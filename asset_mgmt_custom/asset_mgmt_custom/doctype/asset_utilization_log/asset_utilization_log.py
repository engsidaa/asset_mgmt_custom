import frappe
from frappe.model.document import Document


class AssetUtilizationLog(Document):
    def validate(self):
        capacity = self.total_capacity_hours or 0
        used = self.actual_used_hours or 0
        if used > capacity:
            frappe.throw("Actual used hours cannot exceed total capacity hours.")
        self.idle_hours = capacity - used
        self.utilization_pct = round((used / capacity) * 100, 2) if capacity else 0
