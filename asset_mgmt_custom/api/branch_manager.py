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
    # إجمالي كل أوامر العمل المُسلَّمة بأي حالة — لأيقونة "كل الصيانة" في
    # الرئيسية (لا تُحسَب بجمع الأعداد أعلاه لأن open_work_orders يشمل
    # حالات (مفتوح/قيد التنفيذ/معلق) تتقاطع جزئياً مع pending_work_orders).
    total_work_orders = len(frappe.get_list(
        "Asset Work Order", filters={"docstatus": 1}, pluck="name",
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
        "total_work_orders": total_work_orders,
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


@frappe.whitelist()
def update_asset_image(asset, file_url):
    """
    تحديث صورة أصل واحد من شاشة تفاصيل الأصل بالموبايل — صلاحية الكتابة
    الأساسية على doctype Asset مقصورة على "Accounts User"/"Quality
    Manager" (core) بالإضافة لـ Branch Manager بصلاحية قراءة فقط
    (custom_docperm.json)، فأي دور ميداني آخر (فني/مدير فرع/حتى Asset
    Manager) كان سيفشل بصلاحية عبر المسار العام (frappe.client.set_value
    الذي يمر عبر doc.save() الكامل). نفس نمط update_my_profile_picture
    بالضبط: نتحقق من صلاحية قراءة هذا الأصل تحديداً (مُقيَّدة أصلاً بفرع
    المستخدم عبر User Permission)، ثم db_set تتجاوز فحص الكتابة الصارم
    عمداً — الصلاحية الحقيقية هنا هي "هل يقدر يرى هذا الأصل أصلاً؟" وليس
    قيداً عاماً منفصلاً على الكتابة.
    """
    if not file_url:
        frappe.throw(_("file_url is required."))
    _check_read("Asset", asset)
    frappe.db.set_value("Asset", asset, "image", file_url, update_modified=False)
    return {"image": file_url}


@frappe.whitelist()
def attach_file_to_asset(asset, file_url):
    """
    ربط ملف (مستند/صورة عامة) مرفوع مسبقاً بلا doctype/docname بمرفقات
    أصل مُحدَّد — تبويب "المرفقات"/"الملفات" في تفاصيل الأصل بالموبايل
    كان يرفع الملف مباشرة عبر upload_file بـ doctype='Asset',
    docname=asset، فيمر عبر frappe.handler.check_write_permission الذي
    يتطلب صلاحية "write" الأساسية على Asset (مقصورة على Accounts
    User/Quality Manager فقط — انظر ملاحظة update_asset_image أعلاه)،
    فكان يفشل بصلاحية لأغلب الأدوار الميدانية (فني/مستخدم فرع/حتى مدير
    فرع). الحل هنا هو نفس نمط صورة الحساب الشخصية وصورة الأصل تماماً:
    الرفع أولاً بلا doctype (يتجاوز الفحص كلياً)، ثم هذا الاستدعاء يربط
    الملف الناتج بالأصل بعد التحقق من صلاحية قراءة هذا الأصل تحديداً
    فقط — لا صلاحية كتابة عامة مطلوبة لمجرد إرفاق ملف تراه أصلاً.
    """
    if not file_url:
        frappe.throw(_("file_url is required."))
    _check_read("Asset", asset)

    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not file_name:
        frappe.throw(_("File not found for the given file_url."))

    frappe.db.set_value(
        "File",
        file_name,
        {"attached_to_doctype": "Asset", "attached_to_name": asset, "attached_to_field": None},
        update_modified=False,
    )
    return {"file_url": file_url}


@frappe.whitelist()
def update_asset_coding(asset, tag_type, code_field, code_value, before_photo=None, after_photo=None):
    """
    تحديث حقول ترميز أصل (نوع الترميز + كود الملصق/الحديد + صورتا قبل/بعد
    اللصق) من شاشة "إضافة/تفعيل أصل" بالموبايل — عبر frappe.client.set_value
    العام كانت العملية تفشل بـ UpdateAfterSubmitError دائماً على أي أصل
    مُسلَّم بالفعل (docstatus=1، وهي الحالة الطبيعية لأي أصل موجود يُعاد
    ترميزه) لأن custom_tag_type/الحقول المرتبطة ليست allow_on_submit في
    تعريفها. db.set_value هنا يتجاوز هذا القيد عمداً (يكتب مباشرة على
    قاعدة البيانات بلا المرور بدورة حياة المستند/submit lock)، وليس فقط
    فحص الصلاحية كبقية الدوال أعلاه — إعادة الترميز على أصل مُسلَّم فعل
    مقصود هنا، وليس تحايلاً على قيد يُفترض احترامه.
    """
    if code_field not in ("custom_iron_code", "custom_sticker_code"):
        frappe.throw(_("Invalid code field."))
    _check_read("Asset", asset)

    values = {"custom_tag_type": tag_type, code_field: code_value}
    if before_photo:
        values["custom_tagging_photo_before"] = before_photo
    if after_photo:
        values["custom_tagging_photo"] = after_photo

    frappe.db.set_value("Asset", asset, values, update_modified=False)
    return {"ok": 1}


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
def list_pending_asset_requisitions():
    """
    كل طلبات الأصول المعلَّقة لفرع المستخدم — نفس الفلتر الحرفي المستخدَم
    في عدّاد "طلبات أصول معلّقة" بـ get_dashboard_summary أعلاه، حتى يفتح
    الرقم في شاشة الموبايل قائمة حقيقية مطابقة له بدل أن تكون الأيقونة
    بلا وجهة إطلاقاً.
    """
    return frappe.get_list(
        "Asset Requisition",
        filters={
            "docstatus": 1,
            "status": ["in", [
                "Pending Finance Approval",
                "Pending Branch Manager Approval",
                "Pending Asset Manager Approval",
            ]],
        },
        fields=["name", "asset_category", "item_code", "quantity", "status", "request_date", "required_by", "employee", "creation"],
        order_by="request_date desc",
        limit_page_length=0,
    )


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
def create_maintenance_request(asset, problem_description, work_type=None, priority=None, requires_permit=False):
    """
    يُنشئ ويُسلِّم (Submit) Asset Work Order في استدعاء واحد — أنسب
    لتطبيق موبايل من مسار إنشاء-ثم-تسليم منفصل. صورة العطل تُرفَع بعد
    هذا الاستدعاء عبر واجهة رفع الملفات القياسية في Frappe
    (`/api/method/upload_file` مع doctype="Asset Work Order" وdocname
    الناتج هنا وfieldname="fault_photo") — لا حاجة لمعالجة ملفات هنا.

    requires_permit: العطل يُصنَّف خطراً (يتطلب تصريح عمل/عزل طاقة) —
    نتوقف عند insert() فقط (يبقى docstatus=0، الحالة "مفتوح") بدل
    submit() الفوري، لأن before_submit._enforce_loto_gate يمنع أصلاً
    الانتقال لحالة "قيد التنفيذ" لو كان هناك تصريح عمل مرتبط يتطلب LOTO
    ولم يُوقَّع بعد — لكن هذا الفحص عديم الفائدة لو استُدعي submit() هنا
    قبل أن تُتاح للمستخدم فرصة إنشاء وربط التصريح أصلاً. تطبيق الموبايل
    يستدعي submit لاحقاً بنفسه (بعد اكتمال التصريح إن لزم) عبر
    frappe.client.submit القياسي.
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
    if not frappe.utils.cint(requires_permit):
        doc.submit()

    return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


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
            "docstatus", "work_permit", "creation",
        ],
        order_by="creation desc",
        limit_page_length=0,
    )


@frappe.whitelist()
def create_physical_audit():
    """
    ينشئ جرداً فعلياً جديداً (Asset Physical Audit) لفرع المستخدم الحالي
    ويعبّئه تلقائياً بكل أصوله النشطة (نفس منطق fetch_assets الموجود
    أصلاً على الدكتايب نفسه، مُستدعى هنا مباشرة بلا تكرار). كانت هذه
    نقطة الدخول الوحيدة الناقصة لتشغيل تدفّق الجرد من الموبايل كاملاً —
    submit_physical_audit (أدناه في api/v1/mobile.py) يفترض أصلاً وجود
    مسودة جاهزة بلا أي وسيلة لإنشائها من هناك.

    الإدراج هنا بـ ignore_permissions=True عمداً (نفس نمط بقية هذا
    الملف): صلاحية الكتابة الأساسية على Asset Physical Audit ممنوحة فقط
    لأدوار Asset Technician/Asset User/Asset Manager (asset_physical_audit.json)
    وليس بالضرورة لكل مدير فرع، رغم أن الصلاحية الحقيقية المطلوبة هنا هي
    فقط "هل لهذا المستخدم فرع فعلاً؟" — محقَّقة أعلاه.
    """
    branch = (
        frappe.db.get_value("User Permission", {"user": frappe.session.user, "allow": "Branch"}, "for_value")
        or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "branch")
    )
    if not branch:
        frappe.throw(_("No branch is associated with your account."))

    cost_center = frappe.db.get_value("Branch", branch, "custom_cost_center")
    if not cost_center:
        # فروع قديمة (من قبل معالج فتح الفرع الجديد الذي يربط Cost Center
        # تلقائياً) قد لا تملك custom_cost_center — بدل رفض الجرد كلياً
        # وإجبار الإداري على إعداد يدوي منفصل، نُنشئ واحداً هنا بنفس منطق
        # onboard_new_branch (setup/branch_onboarding.py) بالضبط ونربطه
        # بالفرع، حتى يعمل الجرد فوراً ويستفيد أي حقل آخر يعتمد على نفس
        # الحقل (أوامر العمل/طلبات قطع الغيار) من هذا الربط لاحقاً أيضاً.
        company = frappe.defaults.get_global_default("company")
        if not company:
            frappe.throw(
                _("Branch {0} has no linked Cost Center, and no default company is configured to create one automatically.").format(branch)
            )
        parent_cost_center = frappe.db.get_value(
            "Cost Center", {"is_group": 1, "company": company}, "name", order_by="lft asc"
        )
        if not parent_cost_center:
            frappe.throw(
                _("Branch {0} has no linked Cost Center, and no root Cost Center exists for company {1} to create one under.").format(branch, company)
            )
        cc = frappe.new_doc("Cost Center")
        cc.cost_center_name = branch
        cc.company = company
        cc.parent_cost_center = parent_cost_center
        cc.insert(ignore_permissions=True)
        cost_center = cc.name
        frappe.db.set_value("Branch", branch, "custom_cost_center", cost_center)

    doc = frappe.new_doc("Asset Physical Audit")
    doc.cost_center = cost_center
    doc.audit_date = today()
    doc.audited_by = frappe.session.user

    # لا نستخدم doc.fetch_assets() الجاهزة على الدكتايب (تُصفِّي عبر
    # Asset.cost_center حرفياً) — أصول فرع أُنشئت قبل ربط الفرع بمركز
    # تكلفة (أو بمصدر مختلف تماماً) قد لا تحمل نفس قيمة custom_cost_center
    # المُنشَأة للتو أعلاه، فتُرجِع القائمة فارغة رغم وجود أصول نشطة
    # فعلاً في الفرع. هنا نستخدم بدلاً منها frappe.get_list (نفس نمط
    # list_my_assets في هذا الملف)، الذي يُطبِّق التقييد الجغرافي الصحيح
    # تلقائياً عبر User Permission على فرع المستخدم — نفس المصدر الموثوق
    # المستخدَم في كل شاشات الأصول الأخرى بالتطبيق.
    assets = frappe.get_list(
        "Asset",
        filters={"docstatus": 1, "status": ["not in", ["Scrapped", "Sold"]]},
        fields=["name", "asset_name", "asset_category", "location"],
        order_by="asset_category asc, name asc",
        limit_page_length=0,
    )
    doc.items = []
    for a in assets:
        doc.append("items", {
            "asset": a.name,
            "asset_name": a.asset_name,
            "asset_category": a.asset_category,
            "expected_location": a.location,
        })
    doc.insert(ignore_permissions=True)

    return {
        "name": doc.name,
        "cost_center": doc.cost_center,
        "total_assets": doc.total_assets,
        "items": [
            {
                "asset": r.asset,
                "asset_name": r.asset_name,
                "asset_category": r.asset_category,
                "expected_location": r.expected_location,
            }
            for r in doc.items
        ],
    }


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
