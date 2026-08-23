import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AssetRetentionRequest(Document):
    def validate(self):
        self._check_travel_dates()

    def _check_travel_dates(self):
        if self.travel_start and self.travel_end:
            if getdate(self.travel_end) < getdate(self.travel_start):
                frappe.throw(
                    _("Travel End Date cannot be before Travel Start Date."),
                    title=_("Invalid Travel Dates"),
                )
