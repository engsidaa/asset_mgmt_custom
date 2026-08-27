import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, date_diff


class AssetLoan(Document):
    def validate(self):
        if self.expected_return_date and self.loan_date:
            if self.expected_return_date < self.loan_date:
                frappe.throw(_("Expected Return Date cannot be before Loan Date"))

        if self.actual_return_date and self.status != "Returned":
            self.status = "Returned"

    def on_submit(self):
        # Store original custodian before overriding
        asset = frappe.get_doc("Asset", self.asset)
        self.db_set("original_custodian", asset.custodian, update_modified=False)
        # Update asset custodian to the borrower's employee
        frappe.db.set_value("Asset", self.asset, "custodian", self.loaned_to)
        self._notify_loan()

    def on_cancel(self):
        # Restore original custodian
        if self.original_custodian:
            frappe.db.set_value("Asset", self.asset, "custodian", self.original_custodian)

    def _notify_loan(self):
        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": _("Asset {0} loaned to {1}").format(
                    self.asset_name or self.asset, self.loaned_to_name or self.loaned_to),
                "email_content": _("Asset <b>{0}</b> has been loaned to <b>{1}</b>. "
                                   "Expected return: <b>{2}</b>.").format(
                    self.asset_name, self.loaned_to_name, self.expected_return_date),
                "document_type": "Asset Loan",
                "document_name": self.name,
                "for_user": frappe.session.user,
                "type": "Alert",
            }).insert(ignore_permissions=True)
        except Exception:
            pass
