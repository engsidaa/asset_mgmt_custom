import frappe
from frappe.model.document import Document


class AssetEmployeeAllocation(Document):
	def validate(self):
		if self.allocation_date and self.expected_return_date:
			from frappe.utils import getdate

			if getdate(self.expected_return_date) < getdate(self.allocation_date):
				frappe.throw("Expected Return Date cannot be before Allocation Date.")

	def on_submit(self):
		self.db_set("status", "Active")

	def on_cancel(self):
		self.db_set("status", "Returned")
