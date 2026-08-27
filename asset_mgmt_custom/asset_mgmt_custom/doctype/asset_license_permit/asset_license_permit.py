import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today


class AssetLicensePermit(Document):
	def validate(self):
		self._update_status()

	def _update_status(self):
		if not self.expiry_date:
			return
		days_left = date_diff(self.expiry_date, today())
		if days_left < 0:
			self.status = "Expired"
		elif days_left <= (self.renewal_reminder_days or 30):
			self.status = "Pending Renewal"
		else:
			self.status = "Active"
