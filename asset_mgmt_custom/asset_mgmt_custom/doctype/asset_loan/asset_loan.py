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

    @frappe.whitelist()
    def record_return(self, actual_return_date, return_condition):
        """
        زر "Record Return" في الواجهة كان بيستخدم frappe.client.set_value
        العام مباشرة — بيضبط status/actual_return_date/return_condition
        بس، وأبداً معيدش عهدة الأصل (custodian) للشخص الأصلي. الاسترداد
        الوحيد كان بيحصل عند إلغاء (Cancel) المستند بالكامل، مش عند
        "الإرجاع" العادي — يعني الأصل كان فعلياً بيفضل في عهدة المقترض
        للأبد حتى بعد تسجيل إرجاعه في الشاشة.
        """
        if self.status != "Active":
            frappe.throw(_("Only an Active loan can be marked as returned."))

        self.db_set({
            "actual_return_date": actual_return_date,
            "return_condition": return_condition,
            "status": "Returned",
        })

        if self.original_custodian:
            frappe.db.set_value("Asset", self.asset, "custodian", self.original_custodian)
        else:
            frappe.db.set_value("Asset", self.asset, "custodian", "")

        return self.status

    def _notify_loan(self):
        # كانت بتضبط for_user = frappe.session.user، يعني بتبلّغ الشخص اللي
        # عمل الإجراء بنفسه (وهو أصلاً عارف إنه عمله) — مش أي حد محتاج
        # يتابع فعلاً. الصح إشعار أصحاب دور "Asset Manager" (نفس النمط
        # المُستخدَم في باقي التطبيق) بدل تبليغ الشخص لنفسه.
        try:
            recipients = [r[0] for r in frappe.db.sql("""
                SELECT u.name
                FROM `tabUser` u
                JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
                WHERE hr.role = 'Asset Manager' AND u.enabled = 1
                  AND u.name NOT IN ('Administrator', 'All', 'Guest')
            """)]
            if not recipients:
                return

            from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
            enqueue_create_notification(
                users=recipients,
                doc=frappe._dict(
                    subject=_("Asset {0} loaned to {1}").format(
                        self.asset_name or self.asset, self.loaned_to_name or self.loaned_to),
                    email_content=_("Asset <b>{0}</b> has been loaned to <b>{1}</b>. "
                                    "Expected return: <b>{2}</b>.").format(
                        self.asset_name, self.loaned_to_name, self.expected_return_date),
                    document_type="Asset Loan",
                    document_name=self.name,
                    from_user=frappe.session.user,
                    type="Alert",
                ),
            )
        except Exception:
            frappe.log_error(title="asset_loan: failed to notify Asset Managers")
