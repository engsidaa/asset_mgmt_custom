import frappe
from frappe.model.document import Document
from frappe import _


class AssetMaintenanceBudget(Document):
    def validate(self):
        if self.preventive_budget and self.corrective_budget and self.amc_budget:
            allocated = (self.preventive_budget or 0) + (self.corrective_budget or 0) + (self.amc_budget or 0)
            if allocated > (self.total_budget or 0):
                frappe.throw(
                    _("Sum of sub-budgets ({0}) exceeds Total Budget ({1}).").format(
                        frappe.format_value(allocated, {"fieldtype": "Currency"}),
                        frappe.format_value(self.total_budget, {"fieldtype": "Currency"}),
                    )
                )
