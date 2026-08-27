import frappe
from frappe import _
from frappe.model.document import Document


class AssetDisposalRequest(Document):
    def validate(self):
        if self.asset:
            bv = frappe.db.get_value("Asset", self.asset, "value_after_depreciation")
            self.book_value = bv or 0

    def on_submit(self):
        self.db_set("status", "Pending Approval")
        self._notify_managers()

    def _notify_managers(self):
        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
        recipients = [r[0] for r in frappe.db.sql("""
            SELECT u.name
            FROM `tabUser` u
            JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
            WHERE hr.role = 'Assets Manager' AND u.enabled = 1
        """)]
        if not recipients:
            return
        enqueue_create_notification(
            users=recipients,
            doc=frappe._dict(
                subject=_("Disposal Request: {0}").format(self.asset_name or self.asset),
                email_content=_("A disposal request has been submitted for asset <b>{0}</b>. "
                                "Reason: <b>{1}</b>. Please review and approve.").format(
                    self.asset_name, self.disposal_reason),
                document_type="Asset Disposal Request",
                document_name=self.name,
                from_user=frappe.session.user,
                type="Alert",
            ),
        )

    @frappe.whitelist()
    def approve(self):
        if self.status != "Pending Approval":
            frappe.throw(_("Only Pending Approval requests can be approved"))
        self.db_set("status", "Approved")
        self.db_set("approved_by", frappe.session.user)
        self.db_set("approval_date", frappe.utils.today())
        frappe.msgprint(_("Disposal request approved. Proceed to scrap the asset in ERPNext."), alert=True)

    @frappe.whitelist()
    def reject(self, reason=""):
        if self.status != "Pending Approval":
            frappe.throw(_("Only Pending Approval requests can be rejected"))
        self.db_set("status", "Rejected")
        self.db_set("rejection_reason", reason)
