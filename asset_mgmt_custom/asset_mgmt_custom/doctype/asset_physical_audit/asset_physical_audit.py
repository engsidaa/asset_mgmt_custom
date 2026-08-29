import frappe
from frappe import _
from frappe.utils import now_datetime


class AssetPhysicalAudit(frappe.model.document.Document):
    def validate(self):
        self._compute_summary()

    def on_submit(self):
        self.db_set("audit_status", "Completed")
        self._log_audit_activity()
        self._notify_managers_of_issues()

    def _compute_summary(self):
        self.total_assets = len(self.items)
        self.found_count = sum(1 for r in self.items if r.audit_result == "Found")
        self.missing_count = sum(1 for r in self.items if r.audit_result == "Missing")
        self.damaged_count = sum(1 for r in self.items if r.audit_result == "Damaged")

    def _log_audit_activity(self):
        for row in self.items:
            if row.audit_result in ("Missing", "Damaged"):
                try:
                    frappe.get_doc({
                        "doctype": "Asset Activity",
                        "asset": row.asset,
                        "subject": "Physical Audit {0}: asset marked as {1}. Remarks: {2}".format(
                            self.name, row.audit_result, row.remarks or "-"),
                        "user": frappe.session.user,
                        "date": now_datetime(),
                    }).insert(ignore_permissions=True, ignore_links=True)
                except Exception:
                    pass

    def _notify_managers_of_issues(self):
        issues = [r for r in self.items if r.audit_result in ("Missing", "Damaged")]
        if not issues:
            return

        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
        managers = [r[0] for r in frappe.db.sql("""
            SELECT u.name FROM `tabUser` u
            JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
            WHERE hr.role = 'Asset Manager' AND u.enabled = 1
        """)]
        if not managers:
            return

        asset_list = ", ".join(
            "<b>{0}</b> ({1})".format(r.asset_name or r.asset, r.audit_result)
            for r in issues
        )
        enqueue_create_notification(
            users=managers,
            doc=frappe._dict(
                subject=_("Physical Audit {0}: {1} issue(s) found").format(self.name, len(issues)),
                email_content=_("Audit for cost center <b>{0}</b> on <b>{1}</b> found issues: {2}").format(
                    self.cost_center, self.audit_date, asset_list),
                document_type="Asset Physical Audit",
                document_name=self.name,
                from_user=frappe.session.user,
                type="Alert",
            ),
        )

    @frappe.whitelist()
    def fetch_assets(self):
        if not self.cost_center:
            frappe.throw(_("Please set a Branch / Cost Center first"))

        assets = frappe.db.sql("""
            SELECT name, asset_name, asset_category, location
            FROM `tabAsset`
            WHERE docstatus = 1
              AND cost_center = %(cost_center)s
              AND status NOT IN ('Scrapped', 'Sold')
            ORDER BY asset_category, name
        """, {"cost_center": self.cost_center}, as_dict=True)

        self.items = []
        for a in assets:
            self.append("items", {
                "asset": a.name,
                "asset_name": a.asset_name,
                "asset_category": a.asset_category,
                "expected_location": a.location,
                "audit_result": "",
            })

        return len(assets)
