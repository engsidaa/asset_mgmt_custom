import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class AssetBooking(Document):
    def validate(self):
        if get_datetime(self.to_datetime) <= get_datetime(self.from_datetime):
            frappe.throw("To datetime must be after From datetime.")
        self._check_conflicts()

    def _check_conflicts(self):
        conflict = frappe.db.sql("""
            SELECT name FROM `tabAsset Booking`
            WHERE asset = %s AND name != %s AND docstatus = 1
              AND status IN ('Approved', 'Pending')
              AND NOT (%s >= to_datetime OR %s <= from_datetime)
        """, (self.asset, self.name or '', self.from_datetime, self.to_datetime))
        if conflict:
            frappe.throw(f"Asset is already booked during this period. Conflicting booking: {conflict[0][0]}")

    def on_submit(self):
        if self.status == "Pending":
            self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Cancelled")
