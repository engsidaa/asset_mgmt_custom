"""Scheduled tasks for asset_mgmt_custom."""
import frappe
from frappe import _
from frappe.utils import date_diff, today, add_days, now_datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_manager_users():
    return [r[0] for r in frappe.db.sql("""
        SELECT u.name
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Assets Manager' AND u.enabled = 1
    """)]


def _get_manager_emails():
    return [r[0] for r in frappe.db.sql("""
        SELECT u.email
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Assets Manager'
          AND u.enabled = 1
          AND u.name NOT IN ('Administrator', 'All', 'Guest')
          AND u.email IS NOT NULL AND u.email != ''
    """)]


def _create_notification(subject, content, doc_type, doc_name, users):
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
    if not users:
        return
    enqueue_create_notification(
        users=users,
        doc=frappe._dict(
            subject=subject,
            email_content=content,
            document_type=doc_type,
            document_name=doc_name,
            from_user=frappe.session.user or "Administrator",
            type="Alert",
        ),
    )


# ---------------------------------------------------------------------------
# Daily: incomplete asset alerts
# ---------------------------------------------------------------------------

def send_incomplete_asset_alerts():
    """
    Daily job: find assets that have been in 'Incomplete' status for > 3 days
    and send an in-app notification to users with the 'Assets Manager' role.
    """
    incomplete = frappe.db.sql("""
        SELECT name, asset_name, creation, company
        FROM `tabAsset`
        WHERE custom_operational_status = 'Incomplete'
          AND docstatus = 1
        ORDER BY creation ASC
    """, as_dict=True)

    if not incomplete:
        return

    manager_users = _get_manager_users()

    for asset in incomplete:
        days_old = date_diff(today(), str(asset.creation)[:10])
        if days_old < 3:
            continue
        for user in manager_users:
            try:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": _("Incomplete Asset: {0} ({1} days)").format(
                        asset.asset_name or asset.name, days_old),
                    "email_content": _("Asset <b>{0}</b> has been incomplete for <b>{1} days</b>. "
                                       "Please tag and activate it.").format(
                        asset.asset_name or asset.name, days_old),
                    "document_type": "Asset",
                    "document_name": asset.name,
                    "for_user": user,
                    "type": "Alert",
                }).insert(ignore_permissions=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Daily: maintenance due alerts
# ---------------------------------------------------------------------------

def send_maintenance_due_alerts():
    """
    Daily: notify Assets Managers of maintenance tasks due in <= 7 days or overdue.
    """
    cutoff = add_days(today(), 7)

    tasks = frappe.db.sql("""
        SELECT
            mt.name        AS task_name,
            am.asset_name,
            mt.next_due_date,
            mt.maintenance_type,
            mt.assign_to_name,
            DATEDIFF(mt.next_due_date, CURDATE()) AS days_left
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        WHERE mt.next_due_date IS NOT NULL
          AND mt.next_due_date <= %(cutoff)s
          AND mt.maintenance_status != 'Completed'
        ORDER BY mt.next_due_date ASC
    """, {"cutoff": cutoff}, as_dict=True)

    if not tasks:
        return

    manager_users = _get_manager_users()

    for task in tasks:
        days = task.days_left or 0
        if days < 0:
            subject = _("Overdue Maintenance: {0}").format(task.asset_name)
            content = _("Maintenance task for <b>{0}</b> was due on <b>{1}</b> ({2} days ago). "
                        "Please take action immediately.").format(
                task.asset_name, task.next_due_date, abs(days))
        else:
            subject = _("Maintenance Due in {0} days: {1}").format(days, task.asset_name)
            content = _("Maintenance task for <b>{0}</b> is due on <b>{1}</b>.").format(
                task.asset_name, task.next_due_date)

        _create_notification(subject, content, "Asset Maintenance Task", task.task_name, manager_users)


# ---------------------------------------------------------------------------
# Daily: overdue transit escalation
# ---------------------------------------------------------------------------

def check_overdue_transit(threshold_days=3):
    """
    Daily: escalate Asset Movements still In-Transit beyond threshold_days.
    """
    cutoff = add_days(today(), -threshold_days)

    movements = frappe.db.sql("""
        SELECT name, company, modified
        FROM `tabAsset Movement`
        WHERE docstatus = 1
          AND custom_approval_status = 'Approved'
          AND custom_receipt_confirmed = 0
          AND DATE(modified) <= %(cutoff)s
    """, {"cutoff": cutoff}, as_dict=True)

    if not movements:
        return

    manager_users = _get_manager_users()

    for mv in movements:
        days_old = date_diff(today(), str(mv.modified)[:10])
        subject = _("Asset Movement {0} still In-Transit ({1} days)").format(mv.name, days_old)
        content = _("Asset Movement <b>{0}</b> has not been confirmed as received after "
                    "<b>{1} days</b>. Please follow up with the receiving location.").format(
            mv.name, days_old)
        _create_notification(subject, content, "Asset Movement", mv.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: requisition SLA breach alert
# ---------------------------------------------------------------------------

def check_requisition_sla(sla_hours=48):
    """
    Daily: alert when an Asset Requisition has been Pending Approval for > sla_hours.
    """
    cutoff = frappe.utils.add_to_date(now_datetime(), hours=-sla_hours)

    pending = frappe.db.sql("""
        SELECT name, asset_category, creation
        FROM `tabAsset Requisition`
        WHERE status = 'Pending Approval'
          AND docstatus < 2
          AND creation <= %(cutoff)s
    """, {"cutoff": cutoff}, as_dict=True)

    if not pending:
        return

    manager_users = _get_manager_users()

    for req in pending:
        hours_old = int(date_diff(today(), str(req.creation)[:10]) * 24)
        subject = _("Requisition {0} pending for {1}h — SLA breached").format(req.name, hours_old)
        content = _("Asset Requisition <b>{0}</b> ({1}) has been pending approval for over "
                    "<b>{2} hours</b>. SLA is {3} hours.").format(
            req.name, req.asset_category or "", hours_old, sla_hours)
        _create_notification(subject, content, "Asset Requisition", req.name, manager_users)


# ---------------------------------------------------------------------------
# Weekly: warranty digest email
# ---------------------------------------------------------------------------

def send_warranty_digest_email():
    """
    Weekly: send a summary email of assets with warranty expiring in <= 30 days.
    """
    cutoff = add_days(today(), 30)

    assets = frappe.db.sql("""
        SELECT
            name, asset_name, asset_category, location, custodian,
            custom_warranty_expiry,
            DATEDIFF(custom_warranty_expiry, CURDATE()) AS days_remaining
        FROM `tabAsset`
        WHERE docstatus < 2
          AND custom_under_warranty = 1
          AND custom_warranty_expiry IS NOT NULL
          AND custom_warranty_expiry >= CURDATE()
          AND custom_warranty_expiry <= %(cutoff)s
        ORDER BY custom_warranty_expiry ASC
    """, {"cutoff": cutoff}, as_dict=True)

    if not assets:
        return

    recipient_emails = _get_manager_emails()
    if not recipient_emails:
        return

    rows_html = ""
    for a in assets:
        d = a.days_remaining or 0
        color = "#ef4444" if d <= 14 else "#f59e0b" if d <= 21 else "#10b981"
        rows_html += (
            "<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;'>{a.name}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;'>{a.asset_name}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;'>{a.asset_category or ''}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;'>{a.location or ''}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;'>{a.custom_warranty_expiry}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;"
            f"color:{color};font-weight:bold;'>{d} days</td>"
            "</tr>"
        )

    html = (
        "<div style='font-family:Arial,sans-serif;max-width:800px;'>"
        "<h2 style='color:#1e3a5f;'>Warranty Expiry Digest — تنبيه انتهاء الضمان</h2>"
        f"<p style='color:#64748b;'>Assets with warranty expiring within <b>30 days</b> as of {today()}:</p>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#1e3a5f;color:#fff;'>"
        "<th style='padding:8px 10px;text-align:left;'>Asset</th>"
        "<th style='padding:8px 10px;text-align:left;'>Name</th>"
        "<th style='padding:8px 10px;text-align:left;'>Category</th>"
        "<th style='padding:8px 10px;text-align:left;'>Location</th>"
        "<th style='padding:8px 10px;text-align:left;'>Expiry Date</th>"
        "<th style='padding:8px 10px;text-align:left;'>Days Left</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        "<p style='margin-top:20px;font-size:11px;color:#94a3b8;'>"
        "This is an automated weekly digest from Asset Management Custom.<br>"
        "بريد تلقائي أسبوعي من نظام إدارة الأصول.</p>"
        "</div>"
    )

    subject = _("[Weekly Digest] {0} Assets with Warranty Expiring Soon").format(len(assets))
    frappe.sendmail(
        recipients=recipient_emails,
        subject=subject,
        message=html,
        header=[subject, "orange"],
    )


# ---------------------------------------------------------------------------
# Daily: insurance expiry alerts
# ---------------------------------------------------------------------------

def check_insurance_expiry():
    """
    Daily: notify when asset insurance is expiring in 30, 14, or 7 days.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        assets = frappe.db.sql("""
            SELECT name, asset_name, custom_insurance_provider,
                   custom_insurance_policy_no, custom_insurance_expiry
            FROM `tabAsset`
            WHERE docstatus < 2
              AND custom_insurance_expiry IS NOT NULL
              AND custom_insurance_expiry = %(target)s
        """, {"target": target}, as_dict=True)

        if not assets:
            continue

        manager_users = _get_manager_users()
        for a in assets:
            subject = _("Insurance Expiring in {0} days: {1}").format(days_ahead, a.asset_name)
            content = _("Asset <b>{0}</b> insurance (Policy: {1}, Provider: {2}) "
                        "expires on <b>{3}</b>.").format(
                a.asset_name, a.custom_insurance_policy_no or "N/A",
                a.custom_insurance_provider or "N/A", a.custom_insurance_expiry)
            _create_notification(subject, content, "Asset", a.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: asset loan return reminders
# ---------------------------------------------------------------------------

def check_overdue_loans():
    """
    Daily: remind about overdue asset loans.
    """
    overdue = frappe.db.sql("""
        SELECT name, asset, asset_name, loaned_to, loaned_to_name, expected_return_date,
               DATEDIFF(CURDATE(), expected_return_date) AS days_overdue
        FROM `tabAsset Loan`
        WHERE docstatus = 1
          AND status = 'Active'
          AND expected_return_date < CURDATE()
    """, as_dict=True)

    if not overdue:
        return

    manager_users = _get_manager_users()
    for loan in overdue:
        days = loan.days_overdue or 0
        subject = _("Overdue Asset Loan: {0} ({1} days)").format(loan.asset_name, days)
        content = _("Asset <b>{0}</b> loaned to <b>{1}</b> was due on <b>{2}</b> "
                    "but has not been returned ({3} days overdue).").format(
            loan.asset_name, loan.loaned_to_name or loan.loaned_to,
            loan.expected_return_date, days)
        _create_notification(subject, content, "Asset Loan", loan.name, manager_users)
        frappe.db.set_value("Asset Loan", loan.name, "status", "Overdue", update_modified=False)
