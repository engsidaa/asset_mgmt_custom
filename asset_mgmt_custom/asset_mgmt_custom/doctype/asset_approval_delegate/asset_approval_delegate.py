import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AssetApprovalDelegate(Document):
    def validate(self):
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("'To Date' cannot be before 'From Date'."))
