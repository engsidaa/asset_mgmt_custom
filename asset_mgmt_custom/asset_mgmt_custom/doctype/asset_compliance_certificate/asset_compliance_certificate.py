import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import today


class AssetComplianceCertificate(Document):
    def validate(self):
        if self.issue_date and self.expiry_date and self.issue_date >= self.expiry_date:
            frappe.throw(_("Expiry Date must be after Issue Date."))
        self._update_status()

    def _update_status(self):
        from frappe.utils import getdate, add_days
        if not self.expiry_date:
            return
        expiry = getdate(self.expiry_date)
        td = getdate(today())
        if expiry < td:
            self.status = "Expired"
        elif expiry <= add_days(td, self.renewal_reminder_days or 30):
            self.status = "Pending Renewal"
        else:
            self.status = "Active"
