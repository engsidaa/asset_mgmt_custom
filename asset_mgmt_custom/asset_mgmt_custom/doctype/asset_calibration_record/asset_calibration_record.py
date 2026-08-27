import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class AssetCalibrationRecord(Document):
	def validate(self):
		if self.calibration_date and self.next_calibration_date:
			if getdate(self.next_calibration_date) <= getdate(self.calibration_date):
				frappe.throw("Next Calibration Date must be after Calibration Date.")
