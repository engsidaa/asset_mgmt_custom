import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today, getdate


class AssetSoftwareLicense(Document):
    def validate(self):
        self._update_status()
        if self.used_seats and self.total_seats and self.used_seats > self.total_seats:
            frappe.throw("Used seats cannot exceed total seats.")

    def _update_status(self):
        if not self.expiry_date:
            return
        days_left = date_diff(self.expiry_date, today())
        if days_left < 0:
            self.status = "Expired"
        elif days_left <= (self.renewal_reminder_days or 30):
            self.status = "Expiring Soon"
        else:
            self.status = "Active"
