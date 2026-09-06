"""Scheduled tasks for asset_mgmt_custom."""
import frappe
from frappe import _
from frappe.utils import date_diff, today, add_days, now_datetime, flt


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
    Daily: notify Asset Managers of maintenance tasks due in <= 7 days or
    overdue. Tasks that are actually due (days_left <= 0) also get an Asset
    Work Order auto-generated, instead of only a notification — nothing
    used to act on this alert beyond a human reading it.
    """
    cutoff = add_days(today(), 7)

    tasks = frappe.db.sql("""
        SELECT
            mt.name        AS task_name,
            am.name        AS maintenance_schedule,
            am.asset_name  AS asset,
            mt.next_due_date,
            mt.maintenance_type,
            mt.periodicity,
            mt.assign_to,
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
        asset_display = frappe.db.get_value("Asset", task.asset, "asset_name") or task.asset
        days = task.days_left or 0
        if days < 0:
            subject = _("Overdue Maintenance: {0}").format(asset_display)
            content = _("Maintenance task for <b>{0}</b> was due on <b>{1}</b> ({2} days ago). "
                        "Please take action immediately.").format(
                asset_display, task.next_due_date, abs(days))
        else:
            subject = _("Maintenance Due in {0} days: {1}").format(days, asset_display)
            content = _("Maintenance task for <b>{0}</b> is due on <b>{1}</b>.").format(
                asset_display, task.next_due_date)

        _create_notification(subject, content, "Asset Maintenance Task", task.task_name, manager_users)

        if days <= 0:
            _auto_create_work_order_from_task(task)


# الصيانة المتداخلة (Nested PM Levels): ترتيب الدورية من الأقصر للأطول —
# لو استحقت مهمة أعلى مستوى (مثلاً ربع سنوي) لنفس الأصل في نفس اليوم،
# نتجاهل إنشاء أمر عمل لمهمة أدنى مستوى (مثلاً شهري)، لأن الزيارة
# الأشمل (الأعلى مستوى) تُغطي عملياً فحوصات المستوى الأدنى، ولا داعي
# لفتح أمرين منفصلين لنفس الأصل في نفس اليوم.
PM_PERIODICITY_RANK = {
    "Daily": 1, "Weekly": 2, "Monthly": 3, "Quarterly": 4,
    "Half-yearly": 5, "Yearly": 6, "2 Yearly": 7, "3 Yearly": 8,
}


def _higher_level_pm_due_same_day(asset, periodicity, exclude_task, target_date):
    my_rank = PM_PERIODICITY_RANK.get(periodicity, 0)
    if not my_rank:
        return False

    siblings = frappe.db.sql("""
        SELECT mt.periodicity
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        WHERE am.asset_name = %(asset)s
          AND am.docstatus = 1
          AND mt.name != %(exclude_task)s
          AND mt.next_due_date <= %(target_date)s
          AND mt.maintenance_status != 'Completed'
    """, {"asset": asset, "exclude_task": exclude_task, "target_date": target_date}, as_dict=True)

    return any(PM_PERIODICITY_RANK.get(s.periodicity, 0) > my_rank for s in siblings)


def _auto_create_work_order_from_task(task):
    """
    ينشئ Asset Work Order تلقائياً (كمسودة، لم يُسلَّم بعد) من بند صيانة
    وقائية مُستحَق — بدل الاكتفاء بتنبيه لا يُنتج عنه أي مستند فعلي. يتحقق
    أولاً من عدم وجود أمر عمل سابق لنفس البند (idempotent) عبر
    source_maintenance_task، ثم من عدم وجود مهمة صيانة أعلى مستوى مُستحَقة
    لنفس الأصل في نفس اليوم (انظر _higher_level_pm_due_same_day أعلاه).
    """
    existing = frappe.db.exists(
        "Asset Work Order",
        {"source_maintenance_task": task.task_name, "docstatus": ["<", 2]},
    )
    if existing:
        return

    if not task.asset:
        return

    if task.get("periodicity") and _higher_level_pm_due_same_day(
        task.asset, task.periodicity, task.task_name, today()
    ):
        return

    branch = frappe.db.get_value("Asset", task.asset, "custom_branch")

    wo = frappe.new_doc("Asset Work Order")
    wo.title = _("Preventive Maintenance – {0}").format(
        frappe.db.get_value("Asset", task.asset, "asset_name") or task.asset
    )
    wo.asset = task.asset
    wo.branch = branch
    wo.work_type = "صيانة وقائية"
    wo.priority = "عادي"
    wo.request_date = today()
    if task.assign_to:
        wo.assigned_technician = task.assign_to
    wo.maintenance_schedule = task.maintenance_schedule
    wo.source_maintenance_task = task.task_name
    wo.problem_description = task.get("trigger_reason") or _(
        "Auto-generated from a due preventive maintenance task (next due date: {0})."
    ).format(task.next_due_date)

    try:
        wo.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Auto Work Order creation failed",
            message=frappe.get_traceback(),
        )


# ---------------------------------------------------------------------------
# Daily: meter-reading-triggered PM (dual-trigger scheduling, second half)
# ---------------------------------------------------------------------------

def check_meter_triggered_pm():
    """
    النصف الثاني من "الجدولة مزدوجة المحفز": send_maintenance_due_alerts()
    أعلاه يغطي المحفز الزمني (next_due_date) فقط. هنا: أي Asset
    Maintenance Task حُدِّد له نوع عداد وحد استحقاق (custom_meter_trigger_
    type/value) يُفحَص مقابل آخر قراءة عداد فعلية مسجَّلة لنفس الأصل من
    نفس النوع — لو تجاوز الفرق التراكمي منذ آخر استحقاق (custom_last_
    triggered_meter_value) الحدَّ المحدد، يُنشأ أمر عمل تلقائياً بالضبط
    كما لو استحق بالتاريخ (نفس منطق idempotent/nested-level عبر
    _auto_create_work_order_from_task)، أيهما يسبق الآخر فعلياً.
    """
    tasks = frappe.db.sql("""
        SELECT
            mt.name AS task_name,
            am.name AS maintenance_schedule,
            am.asset_name AS asset,
            mt.periodicity,
            mt.assign_to,
            mt.custom_meter_trigger_type AS meter_type,
            mt.custom_meter_trigger_value AS trigger_value,
            IFNULL(mt.custom_last_triggered_meter_value, 0) AS last_triggered_value
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        WHERE am.docstatus = 1
          AND mt.maintenance_status != 'Completed'
          AND mt.custom_meter_trigger_type IS NOT NULL
          AND mt.custom_meter_trigger_type != ''
          AND IFNULL(mt.custom_meter_trigger_value, 0) > 0
    """, as_dict=True)

    for task in tasks:
        latest_reading = frappe.db.get_value(
            "Asset Meter Reading",
            {"asset": task.asset, "meter_type": task.meter_type},
            "current_reading",
            order_by="reading_date desc",
        )
        if latest_reading is None:
            continue

        delta = flt(latest_reading) - flt(task.last_triggered_value)
        if delta < flt(task.trigger_value):
            continue

        task["next_due_date"] = today()
        task["trigger_reason"] = _(
            "Auto-generated: meter reading trigger reached ({0} {1}, threshold {2})."
        ).format(latest_reading, task.meter_type, task.trigger_value)

        existing_before = frappe.db.exists(
            "Asset Work Order",
            {"source_maintenance_task": task.task_name, "docstatus": ["<", 2]},
        )
        _auto_create_work_order_from_task(task)

        # لا نُقدِّم القراءة المرجعية إلا لو أُنشئ أمر فعلاً هذه المرة (وليس
        # idempotent-skipped بسبب أمر سابق لم يُغلَق بعد) أو تخطياً بسبب
        # مستوى صيانة أعلى — في الحالتين المهمة تبقى "مستحقة" فعلياً حتى
        # تُعالَج، فلا داعي لتصفير عدادها الآن.
        if not existing_before and frappe.db.exists(
            "Asset Work Order", {"source_maintenance_task": task.task_name, "docstatus": ["<", 2]}
        ):
            frappe.db.set_value(
                "Asset Maintenance Task", task.task_name,
                "custom_last_triggered_meter_value", latest_reading,
                update_modified=False,
            )


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
# Daily: IFRS 16 lease amortization (Lessee leases only)
# ---------------------------------------------------------------------------

def process_lease_amortization():
    """
    يومي: يفحص كل عقود الإيجار النشطة التي "نحن المستأجر" فيها
    (lease_direction == "We are the Lessee") وحان تاريخ قسطها التالي
    (next_amortization_date <= اليوم)، ويُرحِّل كل واحد عبر
    frappe.enqueue منفصل — قيد يومية بفائدة/أصل التزام/إهلاك أصل حق
    الاستخدام لكل عقد على حدة (انظر asset_lease.py::_post_monthly_amortization
    لتفاصيل الحساب). مُرحَّل للخلفية تحسباً لعدد كبير من العقود دفعة واحدة.
    """
    leases = frappe.get_all(
        "Asset Lease",
        filters={
            "docstatus": 1,
            "status": "Active",
            "lease_direction": "We are the Lessee",
            "next_amortization_date": ["<=", today()],
        },
        pluck="name",
    )
    for lease_name in leases:
        frappe.enqueue(
            "asset_mgmt_custom.asset_mgmt_custom.doctype.asset_lease.asset_lease.post_monthly_amortization",
            queue="long",
            lease_name=lease_name,
        )


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
    Daily: notify when Asset Spare Part quantity is below minimum_qty, and
    auto-create a draft restocking Material Request when neither is
    already true (Asset Category BOM feature closed the loop on knowing
    what parts an asset needs — this closes the loop on actually
    reordering them instead of relying on someone noticing the alert).
    """
    low_parts = frappe.db.sql("""
        SELECT name, item_name, quantity, minimum_qty, location, item_code
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
        _auto_reorder_spare_part(part)


def _auto_reorder_spare_part(part):
    """
    ينشئ Material Request (Purchase) كمسودة فقط — بنفس نمط
    Asset Requisition.create_purchase_requisition الموجود بالفعل (مسودة
    تنتظر مراجعة بشرية قبل التسليم، وليست طلباً ملزماً تلقائياً بالكامل).
    يتحقق أولاً أنه لا يوجد بالفعل طلب شراء معتمد لنفس الصنف لسه Pending،
    لتفادي تكرار الطلب كل يوم لحد ما حد يعالج الأول.
    """
    if not part.item_code:
        return

    existing = frappe.db.sql("""
        SELECT mri.parent
        FROM `tabMaterial Request Item` mri
        JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE mri.item_code = %s AND mr.docstatus < 2
          AND mr.status IN ('Draft', 'Pending', 'Partially Ordered', 'Partially Received')
        LIMIT 1
    """, part.item_code)
    if existing:
        return

    # هدف إعادة التخزين: ضعف الحد الأدنى — رصيد احتياطي بدل الاكتفاء
    # بالوصول للحد الأدنى بالظبط، فيُعاد الطلب فوراً تاني.
    target_stock = flt(part.minimum_qty) * 2
    reorder_qty = max(target_stock - flt(part.quantity), flt(part.minimum_qty))

    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Purchase"
    mr.transaction_date = today()
    mr.schedule_date = add_days(today(), 14)
    mr.append("items", {
        "item_code": part.item_code,
        "qty": reorder_qty,
        "schedule_date": mr.schedule_date,
    })
    mr.insert(ignore_permissions=True)


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
    """
    Daily: alert managers about open work orders that breached their SLA
    resolution deadline (resolution_due_by, from the matching Asset
    Maintenance SLA Policy). Work orders with no SLA policy applied (no
    policy configured for their priority) fall back to the original fixed
    3-day-since-request no-progress rule.
    """
    now = now_datetime()
    fallback_cutoff = add_days(today(), -3)

    overdue = frappe.db.sql("""
        SELECT name, title, asset, asset_name, assigned_technician, priority,
               request_date, resolution_due_by, sla_policy, sla_breached
        FROM `tabAsset Work Order`
        WHERE docstatus = 1
          AND status IN ('مفتوح', 'قيد التنفيذ')
          AND completion_date IS NULL
          AND (
              (resolution_due_by IS NOT NULL AND resolution_due_by < %(now)s)
              OR (resolution_due_by IS NULL AND request_date <= %(fallback_cutoff)s)
          )
    """, {"now": now, "fallback_cutoff": fallback_cutoff}, as_dict=True)

    if not overdue:
        return

    manager_users = _get_manager_users()
    for wo in overdue:
        if wo.sla_policy:
            subject = _("SLA Breached — Overdue Work Order: {0}").format(wo.title)
            content = _("Work order <b>{0}</b> on asset <b>{1}</b> (priority: {2}) "
                        "breached its SLA resolution deadline of <b>{3}</b>.").format(
                wo.title, wo.asset_name or wo.asset, wo.priority, wo.resolution_due_by)
        else:
            subject = _("Overdue Work Order: {0}").format(wo.title)
            content = _("Work order <b>{0}</b> on asset <b>{1}</b> (priority: {2}) "
                        "has been open since <b>{3}</b> with no completion.").format(
                wo.title, wo.asset_name or wo.asset, wo.priority, wo.request_date)

        first_breach = not wo.sla_breached
        frappe.db.set_value("Asset Work Order", wo.name, "sla_breached", 1, update_modified=False)
        if first_breach:
            _propose_sla_penalty(wo)

        recipients = list(manager_users)
        policy_escalate_to = wo.sla_policy and frappe.db.get_value(
            "Asset Maintenance SLA Policy", wo.sla_policy, "escalate_to"
        )
        if policy_escalate_to and policy_escalate_to not in recipients:
            recipients.append(policy_escalate_to)

        _create_notification(subject, content, "Asset Work Order", wo.name, recipients)

        if wo.priority == "حرج":
            from asset_mgmt_custom.notifications import send_critical_alert
            send_critical_alert(
                subject=subject,
                message=content,
                reference_doctype="Asset Work Order",
                reference_name=wo.name,
            )


# ---------------------------------------------------------------------------
# Weekly: cache Total Cost of Ownership onto each Asset + flag peer outliers
# ---------------------------------------------------------------------------

def refresh_tco_cache():
    """
    تقرير "Asset Total Cost of Ownership" شامل وصحيح بالفعل، لكنه يُعاد
    حسابه بالكامل (عشرات الـ JOINs عبر 8 مصادر تكلفة) في كل مرة يُفتح
    فيها التقرير مباشرة (Script Report متزامن) — غير مناسب لعرضه في لوحات
    تحكم/فلاتر/واجهة API الموبايل بشكل متكرر لأسطول أصول كبير. يُرحَّل هذا
    الحساب هنا للخلفية (مطابقةً لسياسة frappe.enqueue للحسابات التراكمية
    المكلفة) ويُخزَّن ناتجه على حقول مخصصة في Asset نفسه، بدل إعادة حساب
    مباشر عند كل عرض.

    يُعيد استخدام get_data() من التقرير مباشرة (بما فيها منطق مقارنة
    الأصول المتماثلة is_tco_outlier) بدل تكرار نفس استعلامات الـ SQL هنا
    من جديد.
    """
    from asset_mgmt_custom.asset_mgmt_custom.report.asset_total_cost_of_ownership.asset_total_cost_of_ownership import get_data

    rows = get_data({})
    now = now_datetime()

    for row in rows:
        frappe.db.set_value(
            "Asset",
            row.asset,
            {
                "custom_tco": row.tco,
                "custom_annual_tco": row.annual_tco,
                "custom_tco_recommendation": row.recommendation,
                "custom_tco_is_outlier": 1 if row.get("is_tco_outlier") else 0,
                "custom_tco_last_computed": now,
            },
            update_modified=False,
        )


# ---------------------------------------------------------------------------
# Weekly: Asset Health Index (AHI) + auto-draft replacement plan
# ---------------------------------------------------------------------------

CONDITION_SCORE_MAP = {"Excellent": 100, "Good": 75, "Fair": 50, "Poor": 25, "Critical": 0}
AHI_REPLACEMENT_THRESHOLD = 40


def refresh_asset_health_index():
    """
    مؤشر مركَّب لكل أصل (0-100، كلما زاد كان أفضل) — بنفس أسلوب الخصم
    الشفاف المُستخدَم فعلياً في تقرير Branch Health Score (سقف أقصى منفصل
    لكل عامل)، بدل معادلة مغلقة:

      AHI = 100
        − min((100 − نسبة العمر المتبقي) × 0.30, 30)   (سقف 30: العمر المتبقي)
        − min((100 − نتيجة آخر تقييم حالة) × 0.30, 30) (سقف 30: آخر تقييم)
        − min(عدد الأعطال آخر 12 شهراً × 10, 25)        (سقف 25: تكرار الأعطال)
        − min(انحراف درجة حرارة حالي × 15, 15)          (سقف 15: انحراف العداد)

    كل عامل يُعاد استخدامه من بيانات موجودة بالفعل (Finance Book لحساب
    العمر المتبقي، Asset Condition Assessment، Asset Failure Analysis،
    Asset Meter Reading + حدود Asset Category الحرارية من ميزة سلسلة
    التبريد في Phase 4) — لا حسابات مكرَّرة.

    إن انخفض المؤشر عن AHI_REPLACEMENT_THRESHOLD، تُنشأ تلقائياً مسودة
    Asset Replacement Plan (بحالة اعتماد "مسودة" فقط — تتطلب مراجعة
    واعتماد بشرياً، وليست نهائية) إن لم توجد بالفعل مسودة/معتمدة سابقة.
    """
    assets = frappe.get_all(
        "Asset",
        filters={"docstatus": 1, "status": ["not in", ["Scrapped", "Sold"]]},
        fields=["name", "asset_name", "asset_category", "purchase_date", "calculate_depreciation"],
    )
    now = now_datetime()

    for asset in assets:
        remaining_life_pct, rul_months = _asset_remaining_life(asset.name, asset.calculate_depreciation)
        condition_score = _asset_last_condition_score(asset.name)
        failure_count = _asset_failure_count_last_12m(asset.name)
        temp_deviation = _asset_temperature_deviation(asset.name, asset.asset_category)

        deduction = (
            min((100 - remaining_life_pct) * 0.30, 30)
            + min((100 - condition_score) * 0.30, 30)
            + min(failure_count * 10, 25)
            + min(temp_deviation * 15, 15)
        )
        ahi = round(max(100 - deduction, 0), 1)

        frappe.db.set_value(
            "Asset", asset.name,
            {
                "custom_ahi_score": ahi,
                "custom_rul_months": rul_months,
                "custom_ahi_last_computed": now,
            },
            update_modified=False,
        )

        if ahi < AHI_REPLACEMENT_THRESHOLD:
            _ensure_draft_replacement_plan(asset, ahi, rul_months)


def _asset_remaining_life(asset_name, calculate_depreciation):
    """نسبة العمر المتبقي % + العمر المتبقي بالأشهر، من Finance Book
    الأول فقط (نفس ما يعتمده Asset.get_value_after_depreciation() بلا
    تحديد finance_book) — بدل حساب تاريخ يدوي مكرَّر."""
    if not calculate_depreciation:
        return 100, None

    fb = frappe.db.sql("""
        SELECT total_number_of_depreciations, total_number_of_booked_depreciations, frequency_of_depreciation
        FROM `tabAsset Finance Book`
        WHERE parent = %s AND parenttype = 'Asset'
        ORDER BY idx ASC LIMIT 1
    """, asset_name, as_dict=True)
    if not fb or not fb[0].total_number_of_depreciations:
        return 100, None

    total = fb[0].total_number_of_depreciations
    booked = fb[0].total_number_of_booked_depreciations or 0
    remaining = max(total - booked, 0)
    pct = round((remaining / total) * 100, 1)
    rul_months = remaining * (fb[0].frequency_of_depreciation or 1)
    return pct, rul_months


def _asset_last_condition_score(asset_name):
    condition = frappe.db.get_value(
        "Asset Condition Assessment", {"asset": asset_name},
        "overall_condition", order_by="assessment_date desc",
    )
    if not condition:
        return 70  # لا يوجد تقييم مسجَّل بعد — قيمة محايدة، لا تُعاقِب أصلاً لم يُقيَّم أصلاً
    return CONDITION_SCORE_MAP.get(condition, 70)


def _asset_failure_count_last_12m(asset_name):
    return frappe.db.count(
        "Asset Failure Analysis",
        filters={"asset": asset_name, "failure_date": [">=", add_days(today(), -365)]},
    )


def _asset_temperature_deviation(asset_name, asset_category):
    if not asset_category:
        return 0
    limits = frappe.db.get_value(
        "Asset Category", asset_category,
        ["custom_min_safe_temperature", "custom_max_safe_temperature"], as_dict=True,
    )
    if not limits or (not limits.custom_min_safe_temperature and not limits.custom_max_safe_temperature):
        return 0

    latest = frappe.db.get_value(
        "Asset Meter Reading", {"asset": asset_name, "meter_type": "درجة الحرارة"},
        "temperature_celsius", order_by="reading_date desc",
    )
    if latest is None:
        return 0

    if (limits.custom_min_safe_temperature and latest < limits.custom_min_safe_temperature) or \
       (limits.custom_max_safe_temperature and latest > limits.custom_max_safe_temperature):
        return 1
    return 0


def _ensure_draft_replacement_plan(asset, ahi, rul_months):
    existing = frappe.db.exists(
        "Asset Replacement Plan",
        {"asset": asset.name, "approval_status": ["in", ["مسودة", "معتمد", "معلق"]]},
    )
    if existing:
        return

    age_years = None
    if asset.purchase_date:
        age_years = round(date_diff(today(), asset.purchase_date) / 365.25, 1)

    plan = frappe.new_doc("Asset Replacement Plan")
    plan.asset = asset.name
    plan.plan_date = today()
    plan.priority = "حرج" if ahi < 20 else "عالٍ"
    plan.replacement_reason = "تكاليف صيانة مرتفعة"
    plan.current_age_years = age_years
    plan.remaining_life_years = round(rul_months / 12, 1) if rul_months else None
    plan.planned_replacement_date = add_days(today(), 90)
    plan.notes = _(
        "مُنشأ تلقائياً: مؤشر صحة الأصل (AHI) وصل إلى {0}% (أقل من حد {1}%). "
        "راجع البيانات وحدِّد ميزانية رأسمالية (CapEx) قبل الاعتماد."
    ).format(ahi, AHI_REPLACEMENT_THRESHOLD)

    try:
        plan.insert(ignore_permissions=True)
        frappe.db.set_value("Asset", asset.name, "custom_replacement_plan", plan.name, update_modified=False)
    except Exception:
        frappe.log_error(title="Auto Replacement Plan creation failed", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# SLA breach penalty proposal (called from check_overdue_work_orders above,
# only the first time a work order transitions into sla_breached=1)
# ---------------------------------------------------------------------------

def _find_matching_vendor_contract(asset, asset_category):
    """أول عقد مورِّد نشط (Active, submitted) يغطي هذا الأصل تحديداً (عبر
    جدول Asset Vendor Contract Asset) أو فئته بالكامل، وله جزاء SLA
    مُحدَّد فعلياً (> صفر) وحساب دائن — نفس منطق مطابقة العقود المُستخدَم
    فعلياً في تقرير TCO لتوزيع تكلفة العقود، بلا تكرار."""
    rows = frappe.db.sql("""
        SELECT vc.name, vc.supplier, vc.penalty_per_sla_breach, vc.penalty_account
        FROM `tabAsset Vendor Contract` vc
        WHERE vc.docstatus = 1 AND vc.status = 'Active'
          AND IFNULL(vc.penalty_per_sla_breach, 0) > 0
          AND vc.penalty_account IS NOT NULL AND vc.penalty_account != ''
          AND (
              vc.asset_category = %(asset_category)s
              OR EXISTS (
                  SELECT 1 FROM `tabAsset Vendor Contract Asset` a
                  WHERE a.parent = vc.name AND a.asset = %(asset)s
              )
          )
        LIMIT 1
    """, {"asset_category": asset_category, "asset": asset}, as_dict=True)
    return rows[0] if rows else None


def _propose_sla_penalty(wo):
    """
    "يقترح النظام تلقائياً إصدار إشعار مدين" — حرفياً: يُقترَح فقط، لا
    يُنفَّذ. يُنشئ Journal Entry **بدون تسليمه** (docstatus يبقى 0،
    مسودة) يخصم الجزاء التعاقدي من حساب مستحقات المورِّد (Payable،
    party_type=Supplier) مقابل حساب الجزاء المحدَّد على العقد — يحتاج
    مراجعة واعتماد المحاسب صراحة قبل التسليم، بنفس أسلوب كل الاقتراحات
    التلقائية الأخرى في هذه المرحلة (Asset Replacement Plan، فاتورة بيع
    التخلص من الأصل).
    """
    asset_category = frappe.db.get_value("Asset", wo.asset, "asset_category")
    contract = _find_matching_vendor_contract(wo.asset, asset_category)
    if not contract:
        return

    company = frappe.db.get_value("Asset", wo.asset, "company") or frappe.defaults.get_user_default("Company")
    payable_account = frappe.db.get_value("Company", company, "default_payable_account")
    if not payable_account:
        return

    penalty = flt(contract.penalty_per_sla_breach)

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = today()
    je.company = company
    je.user_remark = _(
        "Proposed SLA breach penalty against {0} for Asset Work Order {1} (contract {2}) — "
        "DRAFT, review and submit to apply."
    ).format(contract.supplier, wo.name, contract.name)

    ref = {"reference_type": "Asset Work Order", "reference_name": wo.name}
    je.append("accounts", {
        "account": payable_account,
        "party_type": "Supplier",
        "party": contract.supplier,
        "debit_in_account_currency": penalty,
        **ref,
    })
    je.append("accounts", {
        "account": contract.penalty_account,
        "credit_in_account_currency": penalty,
        **ref,
    })

    try:
        je.insert(ignore_permissions=True)  # عمداً بلا submit() — مسودة اقتراح فقط
        frappe.db.set_value(
            "Asset Work Order", wo.name,
            {"vendor_contract": contract.name, "penalty_journal_entry": je.name},
            update_modified=False,
        )
    except Exception:
        frappe.log_error(title="SLA penalty proposal failed", message=frappe.get_traceback())
