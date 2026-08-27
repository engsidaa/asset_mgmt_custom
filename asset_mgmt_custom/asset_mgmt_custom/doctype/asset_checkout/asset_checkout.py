import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AssetCheckout(Document):
    def validate(self):
        if self.checkout_datetime and self.expected_return:
            if self.expected_return <= self.checkout_datetime:
                frappe.throw("Expected Return must be after Checkout Date & Time.")

    def on_submit(self):
        self.db_set("status", "Checked Out")

    def on_cancel(self):
        self.db_set("status", "Returned")
