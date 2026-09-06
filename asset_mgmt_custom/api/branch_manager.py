"""
Branch Manager API
-------------------
واجهة برمجية مخصصة (Whitelisted JSON API) لبوابة مدير الفرع الذاتية —
مصمَّمة من الأساس لتُستهلَك لاحقاً من تطبيق موبايل (وحالياً من واجهة
الديسك العادية كذلك)، وليس صفحات HTML مُصيَّرة على السيرفر.

مبدأ التقييد الجغرافي المُتَّبَع في كل دالة هنا: **لا يوجد فلتر يدوي على
الفرع في أي استعلام** — التقييد يحدث تلقائياً عبر آلية Frappe الأصلية
(User Permission على DocType "Branch"، مضبوطة تلقائياً بواسطة
overrides/branch.py لكل مستخدم مدير فرع). لذلك:

  * كل استدعاء هنا يستخدم `frappe.get_list` حصراً، وليس `frappe.get_all`
    — لأن `frappe.get_all` يضبط `ignore_permissions=True` دائماً
    (يتجاوز User Permission تماماً)، بينما `frappe.get_list` يطبِّقها.
    استخدام `get_all` هنا بالخطأ كان سيُظهر بيانات كل الفروع لأي مستخدم.
  * أي دالة تستقبل اسم مستند محدد من المستخدم (asset، إلخ) تتحقق صراحة
    عبر `frappe.has_permission(..., doc=...)` قبل إرجاع أي بيانات — لأن
    User Permission تُقيِّد فقط ما يظهر في القوائم، ولا تمنع تلقائياً
    استعلاماً مباشراً بمُعرِّف مُخمَّن لمستند خارج الفرع.

**استثناء وحيد صريح:** Asset Movement مستند أساسي بلا أي حقل Link مباشر
لـ Branch (فقط target_location على مستوى كل بند)، فلا تنطبق عليه آلية
User Permission التلقائية إطلاقاً — دوال `list_pending_receipts`/
`confirm_receipt` أسفل هذا الملف تُصفِّي يدوياً بمطابقة
`Branch.custom_default_location` بدل الاعتماد على `get_list`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today


ALLOWED_REMINDER_DOCTYPES = ("Asset Work Order", "Asset", "Asset Requisition")


def _check_read(doctype, name):
    if not frappe.has_permission(doctype, "read", doc=name):
        frappe.throw(
            _("You do not have permission to access {0} {1}.").format(_(doctype), name),
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_dashboard_summary():
    """
    ملخص رقمي واحد لشاشة رئيسية في تطبيق الموبايل — عدد لكل بند بدل ما
    يحتاج التطبيق يعمل 4-5 استدعاءات قوائم منفصلة فقط عشان يعرض أرقاماً.
    كل الأعداد مُقيَّدة تلقائياً بفرع المستخدم الحالي (انظر ملاحظة أعلى
    الملف) — أي مستخدم بلا User Permission على Branch (مش مدير فرع) هياخد
    رجوع القيم اللي يقدر يشوفها فعلاً حسب دوره العادي (صفر لو معندهوش
    صلاحية أصلاً).
    """
    total_assets = len(frappe.get_list("Asset", filters={"docstatus": ["<", 2]}, pluck="name"))

    pending_requisitions = len(frappe.get_list(
        "Asset Requisition",
        filters={
            "docstatus": 1,
            "status": ["in", [
                "Pending Finance Approval",
                "Pending Branch Manager Approval",
                "Pending Asset Manager Approval",
            ]],
        },
        pluck="name",
    ))

    open_work_orders = len(frappe.get_list(
        "Asset Work Order",
        filters={"docstatus": 1, "status": ["in", ["مفتوح", "قيد التنفيذ", "معلق"]]},
        pluck="name",
    ))

    # مؤشرات إضافية لشاشة الصيانة في تطبيق الموبايل — نفس منطق التقييد
    # الجغرافي التلقائي أعلاه (get_list وليس get_all)، بلا استعلامات منفصلة
    # يحتاجها العميل لعرضها.
    pending_work_orders = len(frappe.get_list(
        "Asset Work Order", filters={"docstatus": 1, "status": "مفتوح"}, pluck="name",
    ))
    rejected_work_orders = len(frappe.get_list(
        "Asset Work Order", filters={"docstatus": 1, "status": "مرفوض"}, pluck="name",
    ))
    completed_work_orders = len(frappe.get_list(
        "Asset Work Order", filters={"docstatus": 1, "status": "مكتمل"}, pluck="name",
    ))

    incomplete_assets = len(frappe.get_list(
        "Asset",
        filters={"docstatus": 1, "custom_operational_status": ["in", ["Incomplete", "In Transit"]]},
        pluck="name",
    ))

    my_schedules = frappe.get_list("Asset Maintenance", pluck="name")
    upcoming_maintenance = 0
    if my_schedules:
        cutoff = add_days(today(), 30)
        upcoming_maintenance = frappe.db.sql(
            """
            SELECT COUNT(*) FROM `tabAsset Maintenance Task`
            WHERE parent IN %(schedules)s
              AND maintenance_status != 'Completed'
              AND next_due_date IS NOT NULL
              AND next_due_date <= %(cutoff)s
            """,
            {"schedules": my_schedules, "cutoff": cutoff},
        )[0][0]

    return {
        "total_assets": total_assets,
        "pending_requisitions": pending_requisitions,
        "open_work_orders": open_work_orders,
        "pending_work_orders": pending_work_orders,
        "rejected_work_orders": rejected_work_orders,
        "completed_work_orders": completed_work_orders,
        "incomplete_or_in_transit_assets": incomplete_assets,
        "upcoming_maintenance_tasks": upcoming_maintenance,
    }


@frappe.whitelist()
def get_upcoming_maintenance_tasks(window_days=30):
    """
    نفس عدد "صيانة دورية قادمة" في get_dashboard_summary لكن كصفوف كاملة
    قابلة للعرض (وليس رقماً فقط) — لشاشة "الصيانة الدورية" المخصصة في
    تطبيق الموبايل. يشمل المتأخر فعلياً (is_overdue) والقادم خلال
    window_days معاً، بنفس التقييد الجغرافي التلقائي (get_list على Asset
    Maintenance يُطبِّق User Permission تلقائياً عبر حقلها asset_name).
    """
    schedules = frappe.get_list("Asset Maintenance", pluck="name")
    if not schedules:
        return []

    cutoff = add_days(today(), cint(window_days))
    rows = frappe.db.sql(
        """
        SELECT mt.name, mt.maintenance_task, mt.periodicity, mt.next_due_date,
               mt.maintenance_status, am.name AS maintenance_schedule,
               am.asset_name AS asset, a.asset_name AS asset_display_name,
               a.custom_branch AS branch, a.asset_category AS asset_category
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        JOIN `tabAsset` a ON a.name = am.asset_name
        WHERE am.name IN %(schedules)s
          AND mt.maintenance_status != 'Completed'
          AND mt.next_due_date IS NOT NULL
          AND mt.next_due_date <= %(cutoff)s
        ORDER BY mt.next_due_date ASC
        """,
        {"schedules": schedules, "cutoff": cutoff},
        as_dict=True,
    )

    today_date = getdate(today())
    for row in rows:
        row["is_overdue"] = bool(row.next_due_date and getdate(row.next_due_date) < today_date)
    return rows


@frappe.whitelist()
def list_my_assets(asset_category=None):
    """
    قائمة أصول الفرع — الحقول المختارة هنا فقط هي اللي تطبيق موبايل محتاجها
    لعرض بطاقة أصل (Card)؛ تفاصيله الكاملة تُجلَب لاحقاً عبر get_asset_detail.
    """
    filters = {"docstatus": ["<", 2]}
    if asset_category:
        filters["asset_category"] = asset_category

    return frappe.get_list(
        "Asset",
        filters=filters,
        fields=[
            "name", "asset_name", "asset_category", "image", "status",
            "custom_operational_status", "custom_under_warranty",
            "custom_warranty_expiry", "custom_next_maintenance_date",
        ],
        order_by="asset_name asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def get_asset_detail(asset):
    """
    كل ما يحتاجه مدير الفرع ليعرفه عن جهاز واحد في شاشة تفاصيل بتطبيق
    الموبايل: البيانات الأساسية + المالية + الضمان + الصيانة الدورية +
    أوامر العمل المفتوحة عليه + الملفات المرفقة + التعليقات — في استدعاء
    واحد بدل عدة استدعاءات متفرقة.
    """
    _check_read("Asset", asset)

    asset_doc = frappe.db.get_value(
        "Asset", asset,
        [
            "name", "asset_name", "asset_category", "image", "status",
            "custom_operational_status", "custom_branch", "location",
            "purchase_date", "available_for_use_date", "gross_purchase_amount",
            "value_after_depreciation", "custom_under_warranty", "custom_warranty_expiry",
            "custom_activation_date", "custom_total_maintenance_cost",
            "custom_last_maintenance_date", "custom_next_maintenance_date",
            "custom_sticker_code", "custom_iron_code", "custom_manufacturer_serial",
            # مؤشرات Phase 6/7 (أُضيفت لاحقاً — لم تكن موجودة عند كتابة
            # هذه الدالة أول مرة): تُستخدَم من "لوحة أصل 360" الجديدة،
            # بلا تكرار هذا الاستعلام في دالة منفصلة.
            "custom_ahi_score", "custom_rul_months", "custom_tco",
            "custom_annual_tco", "custom_tco_recommendation", "custom_tco_is_outlier",
        ],
        as_dict=True,
    )
    if not asset_doc:
        frappe.throw(_("Asset {0} not found.").format(asset))

    asset_doc["criticality_level"] = frappe.db.get_value(
        "Asset Criticality Matrix", {"asset": asset}, "criticality_level"
    )

    latest_inspection = frappe.db.get_value(
        "Asset Safety Inspection", {"asset": asset},
        ["name", "inspection_date", "overall_result", "next_inspection_date"],
        order_by="inspection_date desc", as_dict=True,
    )
    asset_doc["last_safety_inspection"] = latest_inspection

    open_work_orders = frappe.get_list(
        "Asset Work Order",
        filters={"asset": asset, "docstatus": ["<", 2]},
        fields=["name", "title", "status", "priority", "work_type", "request_date", "assigned_technician"],
        order_by="creation desc",
        limit_page_length=0,
    )

    work_order_history = _get_work_order_history(asset)

    maintenance_tasks = frappe.db.sql(
        """
        SELECT mt.maintenance_task, mt.periodicity, mt.next_due_date,
               mt.maintenance_status, am.name AS maintenance_schedule
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        WHERE am.asset_name = %(asset)s
        ORDER BY mt.next_due_date ASC
        """,
        {"asset": asset},
        as_dict=True,
    )

    attachments = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Asset", "attached_to_name": asset},
        fields=["name", "file_name", "file_url", "is_private", "creation"],
        order_by="creation desc",
    )

    comments = frappe.get_all(
        "Comment",
        filters={"reference_doctype": "Asset", "reference_name": asset, "comment_type": "Comment"},
        fields=["name", "content", "comment_email", "creation"],
        order_by="creation desc",
    )

    return {
        "asset": asset_doc,
        "open_work_orders": open_work_orders,
        "work_order_history": work_order_history,
        "maintenance_tasks": maintenance_tasks,
        "attachments": attachments,
        "comments": comments,
    }


def _get_work_order_history(asset):
    """
    كل طلبات الصيانة السابقة لنفس الجهاز (وليس فقط المفتوحة منها كما في
    open_work_orders أعلاه) — مع مدة كل طلب من لحظة تقديمه حتى إغلاقه
    فعلياً (سواء بالرفض أو بإتمام الصيانة)، محسوبة هنا مرة واحدة بدل ترك
    حساب التاريخ يتكرر ويختلف بين العميل (Flutter) والديسك مستقبلاً.
    """
    rows = frappe.get_list(
        "Asset Work Order",
        filters={"asset": asset, "docstatus": ["<", 2]},
        fields=[
            "name", "title", "status", "priority", "work_type", "request_date",
            "completion_date", "rejected_on", "assigned_technician",
            "branch_confirmation_status", "branch_rating", "follow_up_work_order",
        ],
        order_by="request_date desc, creation desc",
        limit_page_length=0,
    )
    for row in rows:
        closed_on = None
        if row.status == "مكتمل" and row.completion_date:
            closed_on = row.completion_date
        elif row.status == "مرفوض" and row.rejected_on:
            closed_on = row.rejected_on.date() if hasattr(row.rejected_on, "date") else row.rejected_on

        row["closed_on"] = closed_on
        row["duration_days"] = date_diff(closed_on, row.request_date) if closed_on and row.request_date else None
    return rows


@frappe.whitelist()
def get_new_requisition_context(asset_category=None):
    """
    يُستدعى قبل إنشاء Asset Requisition جديد — يعرض لمدير الفرع كل ما هو
    "معلَّق بالفعل" لفرعه (طلبات لسه Pending، أصول Incomplete/In Transit
    لسه ما اتفعّلتش) حتى لا يُنشئ طلباً مكرراً لشيء في الطريق أصلاً.
    """
    filters = {
        "docstatus": 1,
        "status": ["in", [
            "Pending Finance Approval",
            "Pending Branch Manager Approval",
            "Pending Asset Manager Approval",
            "Approved",
        ]],
    }
    if asset_category:
        filters["asset_category"] = asset_category

    pending_requisitions = frappe.get_list(
        "Asset Requisition",
        filters=filters,
        fields=["name", "asset_category", "quantity", "status", "request_date"],
        order_by="request_date desc",
        limit_page_length=0,
    )

    asset_filters = {"docstatus": 1, "custom_operational_status": ["in", ["Incomplete", "In Transit"]]}
    if asset_category:
        asset_filters["asset_category"] = asset_category

    pending_assets = frappe.get_list(
        "Asset",
        filters=asset_filters,
        fields=["name", "asset_name", "asset_category", "custom_operational_status"],
        order_by="creation desc",
        limit_page_length=0,
    )

    return {
        "pending_requisitions": pending_requisitions,
        "pending_or_in_transit_assets": pending_assets,
    }


@frappe.whitelist()
def create_maintenance_request(asset, problem_description, work_type=None, priority=None):
    """
    يُنشئ ويُسلِّم (Submit) Asset Work Order في استدعاء واحد — أنسب
    لتطبيق موبايل من مسار إنشاء-ثم-تسليم منفصل. صورة العطل تُرفَع بعد
    هذا الاستدعاء عبر واجهة رفع الملفات القياسية في Frappe
    (`/api/method/upload_file` مع doctype="Asset Work Order" وdocname
    الناتج هنا وfieldname="fault_photo") — لا حاجة لمعالجة ملفات هنا.
    """
    _check_read("Asset", asset)

    doc = frappe.new_doc("Asset Work Order")
    doc.title = _("Maintenance Request: {0}").format(
        frappe.db.get_value("Asset", asset, "asset_name") or asset
    )
    doc.asset = asset
    doc.branch = frappe.db.get_value("Asset", asset, "custom_branch")
    doc.work_type = work_type or "إصلاح"
    doc.priority = priority or "عادي"
    doc.problem_description = problem_description
    doc.requested_by = frappe.session.user

    doc.insert()
    doc.submit()

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def list_my_work_orders(status=None, branch=None):
    """
    branch اختياري: تصفية إضافية داخل نطاق ما يقدر المستخدم أصلاً رؤيته
    (لا تُوسِّع الصلاحية بأي شكل — get_list يُطبِّق User Permission تلقائياً
    فوقها كالمعتاد) — مفيدة لمسؤول صيانة مُهيَّأ لعدة فروع/فئات معاً حتى
    يقدر يُركِّز على فرع واحد من قائمة طويلة بدل السكرول فيها كلها.
    """
    filters = {"docstatus": ["<", 2]}
    if status:
        filters["status"] = status
    if branch:
        filters["branch"] = branch

    return frappe.get_list(
        "Asset Work Order",
        filters=filters,
        fields=[
            "name", "title", "asset", "asset_name", "asset_category", "branch", "status", "priority",
            "work_type", "request_date", "completion_date", "actual_cost",
            "assigned_technician", "fault_photo", "branch_confirmation_status",
        ],
        order_by="creation desc",
        limit_page_length=0,
    )


@frappe.whitelist()
def list_accessible_branches():
    """
    قائمة الفروع التي يقدر المستخدم الحالي رؤيتها فعلياً — تُستخدَم لملء
    فلتر الفرع في شاشة "طلبات الصيانة" لمسؤول صيانة مُهيَّأ لأكثر من فرع؛
    get_list (وليس get_all) تعني أن التقييد الجغرافي التلقائي (User
    Permission) يُطبَّق هنا تماماً كباقي دوال هذا الملف.
    """
    return frappe.get_list("Branch", fields=["name", "branch"], order_by="name asc", limit_page_length=0)


@frappe.whitelist()
def add_reminder(reference_doctype, reference_name, reminder_date, note=None):
    """
    "تذكيرات" مدير الفرع تُنفَّذ كـ ToDo عادي (نفس آلية Frappe الأصلية
    للتذكيرات على أي مستند) — لا يوجد مفهوم "تذكير" مخصص منفصل، لتفادي
    اختراع مفهوم Frappe عنده حل جاهز له بالفعل. مقيَّدة بقائمة أنواع
    مستندات محددة (ALLOWED_REMINDER_DOCTYPES) حتى لا تتحول لباب خلفي
    لإنشاء ToDo على أي مستند في النظام.
    """
    if reference_doctype not in ALLOWED_REMINDER_DOCTYPES:
        frappe.throw(_("Reminders are not supported for {0}.").format(reference_doctype))

    _check_read(reference_doctype, reference_name)

    todo = frappe.get_doc({
        "doctype": "ToDo",
        "allocated_to": frappe.session.user,
        "reference_type": reference_doctype,
        "reference_name": reference_name,
        "date": reminder_date,
        "description": note or _("Reminder for {0} {1}").format(_(reference_doctype), reference_name),
    })
    todo.insert()
    return {"name": todo.name}


def _my_managed_locations():
    """المواقع الافتراضية لكل فرع يديره المستخدم الحالي فعلياً."""
    return frappe.get_all(
        "Branch",
        filters={
            "custom_branch_manager": frappe.session.user,
            "custom_default_location": ["is", "set"],
        },
        pluck="custom_default_location",
    )


@frappe.whitelist()
def list_pending_receipts():
    """
    أوامر نقل (Asset Movement من نوع Transfer) لسه محتاجة تأكيد استلام
    فعلي، موجَّهة لمواقع فروع يديرها المستخدم الحالي — التصفية هنا يدوية
    عمداً (انظر ملاحظة أعلى الملف عن سبب استثناء Asset Movement من
    آلية get_list التلقائية).
    """
    locations = _my_managed_locations()
    if not locations:
        return []

    return frappe.db.sql(
        """
        SELECT DISTINCT am.name, am.transaction_date, am.company
        FROM `tabAsset Movement` am
        JOIN `tabAsset Movement Item` ami ON ami.parent = am.name
        WHERE am.docstatus = 1
          AND am.purpose = 'Transfer'
          AND IFNULL(am.custom_receipt_confirmed, 0) = 0
          AND ami.target_location IN %(locations)s
        ORDER BY am.transaction_date DESC
        """,
        {"locations": locations},
        as_dict=True,
    )


@frappe.whitelist()
def confirm_receipt(movement_name):
    """
    اسم موحَّد مع باقي دوال هذا الملف لراحة عميل الموبايل — تُنفِّذ فعلياً
    نفس overrides.asset_movement.confirm_receipt (بما في ذلك فحص
    الصلاحيات فيها) بدون تكرار أي منطق.
    """
    from asset_mgmt_custom.overrides.asset_movement import confirm_receipt as _confirm_receipt
    return _confirm_receipt(movement_name)
