import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class AssetInsuranceRenewal(Document):
    def validate(self):
        if self.new_start_date and self.new_end_date:
            if getdate(self.new_end_date) <= getdate(self.new_start_date):
                frappe.throw("New End Date must be after New Start Date.")

    def on_submit(self):
        self.db_set("renewal_status", "Renewed")
        if self.asset and self.new_insurer and self.new_policy_number and self.new_end_date:
            frappe.db.set_value("Asset", self.asset, {
                "insurer": self.new_insurer,
                "policy_number": self.new_policy_number,
                "insurance_start_date": self.new_start_date,
                "insurance_end_date": self.new_end_date,
            })

    def on_cancel(self):
        self.db_set("renewal_status", "Cancelled")
