import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class AssetWarrantyClaim(Document):
    def validate(self):
        if self.claim_date and self.warranty_expiry_date:
            if getdate(self.claim_date) > getdate(self.warranty_expiry_date):
                frappe.throw("Claim Date cannot be after Warranty Expiry Date.")

    def on_submit(self):
        self.db_set("status", "Submitted")

    def on_cancel(self):
        self.db_set("status", "Open")
