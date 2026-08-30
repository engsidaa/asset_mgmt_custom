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
        WHERE hr.role = 'Asset Manager' AND u.enabled = 1
    """)]


def _get_manager_emails():
    return [r[0] for r in frappe.db.sql("""
        SELECT u.email
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Asset Manager'
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
    and send an in-app notification to users with the 'Asset Manager' role.
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
    Daily: notify Asset Managers of maintenance tasks due in <= 7 days or overdue.
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
    Daily: alert when an Asset Requisition has been pending at any approval
    stage for > sla_hours.

    "Pending Approval" was the single status used by the old one-step
    Workflow, before Phase 4 replaced it with a real 3-stage chain (Finance
    -> Branch Manager -> Asset Manager) and three distinct "Pending * Approval"
    statuses. This job was never updated after that rewrite — it's been
    watching for a status value that hasn't existed since, so the SLA
    breach alert has silently never fired for any real requisition.
    """
    cutoff = frappe.utils.add_to_date(now_datetime(), hours=-sla_hours)

    pending = frappe.db.sql("""
        SELECT name, asset_category, creation
        FROM `tabAsset Requisition`
        WHERE status IN ('Pending Finance Approval', 'Pending Branch Manager Approval',
                          'Pending Asset Manager Approval')
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
    Uses standard ERPNext fields: insurer, policy_number, insurance_end_date.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        assets = frappe.db.sql("""
            SELECT name, asset_name, insurer, policy_number, insurance_end_date
            FROM `tabAsset`
            WHERE docstatus < 2
              AND insurance_end_date IS NOT NULL
              AND insurance_end_date = %(target)s
        """, {"target": target}, as_dict=True)

        if not assets:
            continue

        manager_users = _get_manager_users()
        for a in assets:
            subject = _("Insurance Expiring in {0} days: {1}").format(days_ahead, a.asset_name)
            content = _("Asset <b>{0}</b> insurance (Policy: {1}, Provider: {2}) "
                        "expires on <b>{3}</b>.").format(
                a.asset_name, a.policy_number or "N/A",
                a.insurer or "N/A", a.insurance_end_date)
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


# ---------------------------------------------------------------------------
# Daily: AMC expiry alerts
# ---------------------------------------------------------------------------

def check_amc_expiry():
    """
    Daily: alert when an Asset Maintenance Contract expires in 30, 14, or 7 days,
    and auto-mark contracts as Expired when past their end date.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        contracts = frappe.db.sql("""
            SELECT name, supplier, coverage_type, end_date
            FROM `tabAsset Maintenance Contract`
            WHERE status = 'Active'
              AND end_date = %(target)s
        """, {"target": target}, as_dict=True)

        manager_users = _get_manager_users()
        for c in contracts:
            subject = _("AMC Expiring in {0} days: {1}").format(days_ahead, c.name)
            content = _("Maintenance Contract <b>{0}</b> with supplier <b>{1}</b> "
                        "({2}) expires on <b>{3}</b>. Please arrange renewal.").format(
                c.name, c.supplier, c.coverage_type or "", c.end_date)
            _create_notification(subject, content, "Asset Maintenance Contract", c.name, manager_users)

    # Auto-expire past contracts
    frappe.db.sql("""
        UPDATE `tabAsset Maintenance Contract`
        SET status = 'Expired', modified = NOW()
        WHERE status = 'Active' AND end_date < %(today)s
    """, {"today": today()})


# ---------------------------------------------------------------------------
# Daily: compliance certificate expiry alerts
# ---------------------------------------------------------------------------

def check_compliance_expiry():
    """
    Daily: notify when a compliance/safety certificate is expiring soon.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        certs = frappe.db.sql("""
            SELECT name, certificate_number, certificate_type, asset, asset_name,
                   issuing_authority, expiry_date
            FROM `tabAsset Compliance Certificate`
            WHERE status IN ('Active', 'Pending Renewal')
              AND expiry_date = %(target)s
        """, {"target": target}, as_dict=True)

        if not certs:
            continue

        manager_users = _get_manager_users()
        for c in certs:
            subject = _("Compliance Certificate Expiring in {0} days: {1}").format(
                days_ahead, c.certificate_number)
            content = _("{0} certificate <b>{1}</b> for asset <b>{2}</b> "
                        "(issued by {3}) expires on <b>{4}</b>. Please arrange renewal.").format(
                c.certificate_type or "Compliance",
                c.certificate_number, c.asset_name or c.asset,
                c.issuing_authority or "N/A", c.expiry_date)
            _create_notification(
                subject, content,
                "Asset Compliance Certificate", c.name,
                manager_users
            )

    # Auto-update status on expired certs
    frappe.db.sql("""
        UPDATE `tabAsset Compliance Certificate`
        SET status = 'Expired', modified = NOW()
        WHERE status IN ('Active', 'Pending Renewal')
          AND expiry_date < %(today)s
    """, {"today": today()})


# ---------------------------------------------------------------------------
# Daily: lease expiry alerts
# ---------------------------------------------------------------------------

def check_lease_expiry():
    """
    Daily: notify when an asset lease is expiring in 30, 14, or 7 days.
    Also auto-expire past leases.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        leases = frappe.db.sql("""
            SELECT name, asset, asset_name, lessee_name, lease_type, end_date
            FROM `tabAsset Lease`
            WHERE docstatus = 1
              AND status = 'Active'
              AND end_date = %(target)s
        """, {"target": target}, as_dict=True)

        if not leases:
            continue

        manager_users = _get_manager_users()
        for lease in leases:
            subject = _("Asset Lease Expiring in {0} days: {1}").format(
                days_ahead, lease.asset_name or lease.asset)
            content = _("{0} lease for asset <b>{1}</b> with lessee <b>{2}</b> "
                        "expires on <b>{3}</b>.").format(
                lease.lease_type or "Lease",
                lease.asset_name or lease.asset,
                lease.lessee_name or "N/A", lease.end_date)
            _create_notification(subject, content, "Asset Lease", lease.name, manager_users)

    # Auto-expire past leases
    frappe.db.sql("""
        UPDATE `tabAsset Lease`
        SET status = 'Expired', modified = NOW()
        WHERE docstatus = 1
          AND status = 'Active'
          AND end_date < %(today)s
    """, {"today": today()})


# ---------------------------------------------------------------------------
# Daily: overdue asset checkouts
# ---------------------------------------------------------------------------

def check_overdue_checkouts():
    """
    Daily: notify when an Asset Checkout is overdue (expected_return < now and status = Checked Out).
    """
    overdue = frappe.db.sql("""
        SELECT name, asset, asset_name, checked_out_by, expected_return
        FROM `tabAsset Checkout`
        WHERE docstatus = 1
          AND status = 'Checked Out'
          AND expected_return < %(now)s
    """, {"now": now_datetime()}, as_dict=True)

    if not overdue:
        return

    manager_users = _get_manager_users()
    for co in overdue:
        frappe.db.set_value("Asset Checkout", co.name, "status", "Overdue")
        subject = _("Asset Checkout Overdue: {0}").format(co.asset_name or co.asset)
        content = _("Asset <b>{0}</b> checked out by <b>{1}</b> was due by <b>{2}</b> "
                    "and has not been returned.").format(
            co.asset_name or co.asset, co.checked_out_by, co.expected_return)
        _create_notification(subject, content, "Asset Checkout", co.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: open critical/high incidents
# ---------------------------------------------------------------------------

def check_open_critical_incidents():
    """
    Daily: notify about open Critical or High severity incidents older than 24 hours.
    """
    incidents = frappe.db.sql("""
        SELECT name, asset, severity, incident_date
        FROM `tabAsset Incident Report`
        WHERE docstatus = 1
          AND status IN ('Open', 'Under Investigation')
          AND severity IN ('Critical', 'High')
          AND incident_date < %(cutoff)s
    """, {"cutoff": add_days(today(), -1)}, as_dict=True)

    if not incidents:
        return

    manager_users = _get_manager_users()
    for inc in incidents:
        subject = _("Open {0} Incident: {1}").format(inc.severity, inc.name)
        content = _("Incident <b>{0}</b> (Severity: {1}) for asset <b>{2}</b> "
                    "is still open since <b>{3}</b>.").format(
            inc.name, inc.severity, inc.asset, inc.incident_date)
        _create_notification(subject, content, "Asset Incident Report", inc.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: missed cleaning schedules
# ---------------------------------------------------------------------------

def check_missed_cleaning():
    """
    Daily: mark past Scheduled cleaning tasks as Missed and notify.
    """
    missed = frappe.db.sql("""
        SELECT name, asset, asset_name, cleaning_type, scheduled_date, assigned_to
        FROM `tabAsset Cleaning Schedule`
        WHERE status = 'Scheduled'
          AND scheduled_date < %(today)s
    """, {"today": today()}, as_dict=True)

    if not missed:
        return

    manager_users = _get_manager_users()
    for cs in missed:
        frappe.db.set_value("Asset Cleaning Schedule", cs.name, "status", "Missed")
        subject = _("Missed Cleaning: {0} - {1}").format(
            cs.asset_name or cs.asset, cs.cleaning_type)
        content = _("Cleaning schedule <b>{0}</b> for asset <b>{1}</b> "
                    "(Type: {2}, Assigned to: {3}) was not completed on <b>{4}</b>.").format(
            cs.name, cs.asset_name or cs.asset, cs.cleaning_type,
            cs.assigned_to, cs.scheduled_date)
        _create_notification(subject, content, "Asset Cleaning Schedule", cs.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: spare parts below minimum quantity
# ---------------------------------------------------------------------------

def check_spare_parts_low():
    """
    Daily: notify when Asset Spare Part quantity is below minimum_qty.
    """
    low_parts = frappe.db.sql("""
        SELECT name, item_name, quantity, minimum_qty, location
        FROM `tabAsset Spare Part`
        WHERE minimum_qty > 0 AND quantity < minimum_qty
    """, as_dict=True)

    if not low_parts:
        return

    manager_users = _get_manager_users()
    for part in low_parts:
        subject = _("Low Spare Part Stock: {0}").format(part.item_name)
        content = _("Spare part <b>{0}</b> has only <b>{1}</b> units "
                    "(minimum required: {2}). Location: {3}.").format(
            part.item_name, part.quantity, part.minimum_qty,
            part.location or "N/A")
        _create_notification(subject, content, "Asset Spare Part", part.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: license & permit expiry alerts
# ---------------------------------------------------------------------------

def check_permit_expiry():
    """
    Daily: notify when an Asset License/Permit is expiring in 30, 14, or 7 days.
    Also auto-expire past permits.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        permits = frappe.db.sql("""
            SELECT name, asset, asset_name, permit_type, license_number,
                   issuing_authority, expiry_date
            FROM `tabAsset License Permit`
            WHERE status IN ('Active', 'Pending Renewal')
              AND expiry_date = %(target)s
        """, {"target": target}, as_dict=True)

        if not permits:
            continue

        manager_users = _get_manager_users()
        for p in permits:
            subject = _("Permit Expiring in {0} days: {1} ({2})").format(
                days_ahead, p.permit_type or "Permit", p.asset_name or p.asset)
            content = _("Asset <b>{0}</b> permit <b>{1}</b> (No: {2}, Authority: {3}) "
                        "expires on <b>{4}</b>.").format(
                p.asset_name or p.asset, p.permit_type or "Permit",
                p.license_number or "N/A", p.issuing_authority or "N/A", p.expiry_date)
            _create_notification(subject, content, "Asset License Permit", p.name, manager_users)

    # Auto-expire past permits
    frappe.db.sql("""
        UPDATE `tabAsset License Permit`
        SET status = 'Expired', modified = NOW()
        WHERE status IN ('Active', 'Pending Renewal')
          AND expiry_date < %(today)s
    """, {"today": today()})


# ---------------------------------------------------------------------------
# Daily: calibration due alerts
# ---------------------------------------------------------------------------

def check_calibration_due():
    """
    Daily: notify when Asset Calibration is due in 30, 14, or 7 days.
    """
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        records = frappe.db.sql("""
            SELECT name, asset, asset_name, calibration_date,
                   next_calibration_date, calibrated_by
            FROM `tabAsset Calibration Record`
            WHERE next_calibration_date = %(target)s
        """, {"target": target}, as_dict=True)

        if not records:
            continue

        manager_users = _get_manager_users()
        for r in records:
            subject = _("Asset Calibration Due in {0} days: {1}").format(
                days_ahead, r.asset_name or r.asset)
            content = _("Asset <b>{0}</b> is due for calibration on <b>{1}</b>. "
                        "Last calibrated by: {2} on {3}.").format(
                r.asset_name or r.asset, r.next_calibration_date,
                r.calibrated_by or "N/A", r.calibration_date)
            _create_notification(subject, content, "Asset Calibration Record", r.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: overdue employee allocations
# ---------------------------------------------------------------------------

def check_overdue_allocations():
    """
    Daily: notify when an Asset Employee Allocation is past expected return date.
    """
    overdue = frappe.db.sql("""
        SELECT name, asset, asset_name, employee, employee_name,
               allocation_date, expected_return_date
        FROM `tabAsset Employee Allocation`
        WHERE docstatus = 1
          AND status = 'Active'
          AND expected_return_date IS NOT NULL
          AND expected_return_date < %(today)s
    """, {"today": today()}, as_dict=True)

    if not overdue:
        return

    manager_users = _get_manager_users()
    for a in overdue:
        frappe.db.set_value("Asset Employee Allocation", a.name, "status", "Overdue")
        subject = _("Asset Allocation Overdue: {0} - {1}").format(
            a.asset_name or a.asset, a.employee_name or a.employee)
        content = _("Asset <b>{0}</b> allocated to <b>{1}</b> was due for return by "
                    "<b>{2}</b> and has not been returned yet.").format(
            a.asset_name or a.asset, a.employee_name or a.employee,
            a.expected_return_date)
        _create_notification(subject, content, "Asset Employee Allocation", a.name, manager_users)


# ---------------------------------------------------------------------------
# Daily: software license expiry alerts
# ---------------------------------------------------------------------------

def check_software_license_expiry():
    """Daily: notify when software licenses are expiring in 30, 14, or 7 days."""
    for days_ahead in [30, 14, 7]:
        target = add_days(today(), days_ahead)
        records = frappe.db.sql("""
            SELECT name, software_name, asset, asset_name, license_type,
                   expiry_date, vendor
            FROM `tabAsset Software License`
            WHERE expiry_date = %(target)s
              AND status NOT IN ('Expired', 'Terminated')
        """, {"target": target}, as_dict=True)

        if not records:
            continue

        manager_users = _get_manager_users()
        for r in records:
            subject = _("Software License Expiring in {0} days: {1}").format(
                days_ahead, r.software_name)
            content = _("Software license <b>{0}</b> ({1}) linked to asset "
                        "<b>{2}</b> will expire on <b>{3}</b>.").format(
                r.software_name, r.license_type or "N/A",
                r.asset_name or r.asset or "N/A", r.expiry_date)
            _create_notification(subject, content, "Asset Software License", r.name, manager_users)

    # Auto-expire past due licenses
    frappe.db.sql("""
        UPDATE `tabAsset Software License`
        SET status = 'Expired'
        WHERE expiry_date < %(today)s
          AND status NOT IN ('Expired', 'Terminated')
    """, {"today": today()})


# ---------------------------------------------------------------------------
# Daily: preventive maintenance schedule due alerts
# ---------------------------------------------------------------------------

def check_pm_schedule_due():
    """Daily: notify when ERPNext Asset Maintenance tasks are due (uses built-in Asset Maintenance Task)."""
    manager_users = _get_manager_users()
    for days_ahead in [7, 3, 1]:
        target = add_days(today(), days_ahead)
        records = frappe.db.sql("""
            SELECT
                t.name AS task_name,
                t.maintenance_task,
                t.maintenance_type,
                t.next_due_date,
                t.assign_to_name AS assigned_to,
                am.name AS schedule_name,
                am.asset_name
            FROM `tabAsset Maintenance Task` t
            JOIN `tabAsset Maintenance` am ON am.name = t.parent
            WHERE t.next_due_date = %(target)s
              AND t.maintenance_status IN ('Pending', 'Overdue')
              AND am.docstatus = 1
        """, {"target": target}, as_dict=True)

        if not records:
            continue

        for r in records:
            subject = _("PM موعده بعد {0} يوم: {1} - {2}").format(
                days_ahead, r.asset_name or r.schedule_name, r.maintenance_task)
            content = _("مهمة الصيانة الوقائية <b>{0}</b> للأصل "
                        "<b>{1}</b> موعدها <b>{2}</b> ({3}).").format(
                r.maintenance_task, r.asset_name,
                r.next_due_date, r.maintenance_type)
            _create_notification(subject, content, "Asset Maintenance", r.schedule_name, manager_users)


# ---------------------------------------------------------------------------
# Daily: overdue bookings
# ---------------------------------------------------------------------------

def check_overdue_bookings():
    """Daily: mark approved bookings as Completed if past to_datetime."""
    from frappe.utils import now_datetime as _now
    overdue = frappe.db.sql("""
        SELECT name, asset, asset_name, booked_by, to_datetime
        FROM `tabAsset Booking`
        WHERE docstatus = 1
          AND status = 'Approved'
          AND to_datetime < %(now)s
    """, {"now": str(_now())}, as_dict=True)

    for b in overdue:
        frappe.db.set_value("Asset Booking", b.name, "status", "Completed")


# ---------------------------------------------------------------------------
# Daily: expire work permits past valid_to
# ---------------------------------------------------------------------------

def check_expired_work_permits():
    """Daily: mark submitted work permits as 'منتهي' when valid_to has passed."""
    from frappe.utils import now_datetime as _now
    frappe.db.sql("""
        UPDATE `tabAsset Work Permit`
        SET status = 'منتهي'
        WHERE docstatus = 1
          AND status = 'صالح'
          AND valid_to < %(now)s
    """, {"now": str(_now())})


# ---------------------------------------------------------------------------
# Daily: notify open work orders older than 3 days with no completion date
# ---------------------------------------------------------------------------

def check_overdue_work_orders():
    """Daily: alert managers about open work orders with no progress after 3 days."""
    cutoff = add_days(today(), -3)
    overdue = frappe.db.sql("""
        SELECT name, title, asset, asset_name, assigned_technician, priority, request_date
        FROM `tabAsset Work Order`
        WHERE docstatus = 1
          AND status IN ('مفتوح', 'قيد التنفيذ')
          AND request_date <= %(cutoff)s
          AND completion_date IS NULL
    """, {"cutoff": cutoff}, as_dict=True)

    if not overdue:
        return

    manager_users = _get_manager_users()
    for wo in overdue:
        subject = _("Overdue Work Order: {0}").format(wo.title)
        content = _("Work order <b>{0}</b> on asset <b>{1}</b> (priority: {2}) "
                    "has been open since <b>{3}</b> with no completion.").format(
            wo.title, wo.asset_name or wo.asset, wo.priority, wo.request_date)
        _create_notification(subject, content, "Asset Work Order", wo.name, manager_users)
