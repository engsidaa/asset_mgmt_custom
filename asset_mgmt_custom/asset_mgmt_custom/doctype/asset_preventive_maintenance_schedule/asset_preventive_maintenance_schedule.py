import frappe
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, today


class AssetPreventiveMaintenanceSchedule(Document):
    def validate(self):
        if self.last_done_date and self.frequency_days:
            self.next_due_date = add_days(self.last_done_date, self.frequency_days)
        if self.next_due_date and date_diff(today(), self.next_due_date) > 0:
            self.status = "Overdue"
