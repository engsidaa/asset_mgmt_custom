import frappe
from frappe import _
from frappe.utils import getdate, today


class AssetMaintenanceContract(frappe.model.document.Document):
    def validate(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) < getdate(self.start_date):
                frappe.throw(_("End Date cannot be before Start Date"))
        self._update_status()

    def _update_status(self):
        if self.end_date and getdate(self.end_date) < getdate(today()):
            self.status = "Expired"
