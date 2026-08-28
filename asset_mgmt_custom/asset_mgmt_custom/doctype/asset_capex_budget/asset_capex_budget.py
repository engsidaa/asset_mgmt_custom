import frappe
from frappe.model.document import Document
from frappe import _


class AssetCapExBudget(Document):
    def validate(self):
        allocated = (
            (self.new_acquisition_budget or 0)
            + (self.replacement_budget or 0)
            + (self.upgrade_budget or 0)
        )
        if allocated > (self.total_capex_budget or 0):
            frappe.throw(
                _("Sum of sub-budgets ({0}) exceeds Total CapEx Budget ({1}).").format(
                    frappe.format_value(allocated, {"fieldtype": "Currency"}),
                    frappe.format_value(self.total_capex_budget, {"fieldtype": "Currency"}),
                )
            )
        self._update_item_totals()

    def on_submit(self):
        self.db_set("status", "Approved")

    def _update_item_totals(self):
        for item in self.items or []:
            item.total_cost = (item.quantity or 1) * (item.unit_cost or 0)
