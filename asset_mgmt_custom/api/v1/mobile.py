"""
Headless API — تطبيق Flutter الميداني (فنيّي/مورِّدي الصيانة)
----------------------------------------------------------------
لا توجد أي شاشات هنا عمداً (توجيه صريح من المستخدم) — فقط نقاط اتصال
برمجية (@frappe.whitelist()) بصيغة JSON قياسية، جاهزة للربط المستقبلي.

**الفرق عن `api/branch_manager.py`:** ذلك الملف مخصص لشخصية "مدير
الفرع" (مُقيَّد تلقائياً بفرعه عبر User Permission — انظر توثيقه هو
لتفاصيل هذه الآلية). هذا الملف مخصص لشخصية "الفني/مورِّد الصيانة
الميداني" — قد يعمل على أكثر من فرع، وتقييده الحقيقي هو "المهام
المُسنَدة إليه تحديداً" (assigned_technician) وليس فرعاً بعينه. حيث
يتداخل الاثنان منطقياً (بيانات الأصل، إنشاء بلاغ عطل)، تُعاد دوال
`branch_manager` مباشرة بدل تكرار نفس المنطق.
"""

import json

import frappe
from frappe import _

from asset_mgmt_custom.api.branch_manager import create_maintenance_request, get_asset_detail


@frappe.whitelist()
def get_app_context():
    """
    استدعاء واحد عند فتح تطبيق الموبايل (بعد المصادقة بـ API Key/Secret
    مباشرة — لا يوجد استدعاء "تسجيل دخول" منفصل) يُعيد كل ما يحتاجه
    العميل ليقرر أي شاشات/أزرار يعرضها لهذا المستخدم تحديداً: الاسم،
    الصورة، الأدوار الفعلية (frappe.get_roles — تشمل الأدوار عبر
    المجموعات)، سجل الموظف المرتبط إن وُجد، والفروع التي يديرها هذا
    المستخدم فعلياً (Branch.custom_branch_manager) ليُميَّز بصرياً بين
    "مستخدم فرع" و"فني/مورِّد صيانة ميداني" و"مسؤول صيانة" بلا تخمين في
    العميل نفسه.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Invalid or missing API credentials."), frappe.AuthenticationError)

    employee = frappe.db.get_value(
        "Employee", {"user_id": user},
        ["name", "employee_name", "department", "branch"],
        as_dict=True,
    )

    managed_branches = frappe.get_all(
        "Branch", filters={"custom_branch_manager": user}, pluck="name"
    )

    default_branch = frappe.db.get_value(
        "User Permission", {"user": user, "allow": "Branch"}, "for_value"
    )

    return {
        "user": user,
        "full_name": frappe.db.get_value("User", user, "full_name"),
        "user_image": frappe.db.get_value("User", user, "user_image"),
        "roles": frappe.get_roles(user),
        "employee": employee,
        "managed_branches": managed_branches,
        "default_branch": default_branch,
    }


@frappe.whitelist()
def get_branch_assets(branch):
    """
    قائمة أصول فرع معيّن — للفني المُوفَد لفرع لفحص/صيانة أصوله. يعتمد
    فقط على صلاحية قراءة Asset العادية (ممنوحة أصلاً لدور Asset
    Technician)، وليس على User Permission الخاصة بـ Branch (تلك مخصصة
    لمدراء الفروع أنفسهم، وليس فنيّي الصيانة المتنقلين بين عدة فروع).
    """
    return frappe.get_list(
        "Asset",
        filters={
            "custom_branch": branch,
            "docstatus": 1,
            "status": ["not in", ["Scrapped", "Sold"]],
        },
        fields=[
            "name", "asset_name", "asset_category", "location", "status",
            "custom_operational_status", "custom_coding_status", "image",
        ],
        order_by="asset_category, asset_name",
        limit_page_length=0,
    )


def resolve_asset_identifier(identifier):
    """
    مطابقة كود ممسوح (QR/باركود) أو مُدخَل يدوياً إلى اسم أصل حقيقي —
    اسم الأصل نفسه، أو كود الملصق (Barcode/RFID)، أو كود النقش الحديدي
    (Iron Code)، أو الرقم التسلسلي المطبوع من المصنّع (يُقرأ عادة عبر OCR
    من تطبيق الموبايل للأصول التي لم تُلصَق بملصق داخلي بعد)، أيّها وُجد
    أولاً. نقطة المطابقة الوحيدة في هذا التطبيق — يُستدعى من scan_asset
    هنا ومن أدوات المسح الجماعي (Asset Physical Audit) بلا تكرار المنطق.
    """
    return (
        frappe.db.get_value("Asset", identifier)
        or frappe.db.get_value("Asset", {"custom_sticker_code": identifier})
        or frappe.db.get_value("Asset", {"custom_iron_code": identifier})
        or frappe.db.get_value("Asset", {"custom_manufacturer_serial": identifier})
    )


@frappe.whitelist()
def scan_asset(identifier):
    """
    استعلام فوري بمسح كود QR/باركود أو إدخال الكود يدوياً، ثم يُعيد نفس
    تفاصيل الأصل الكاملة المُستخدَمة أصلاً في بوابة مدير الفرع
    (get_asset_detail) — بلا تكرار.
    """
    asset_name = resolve_asset_identifier(identifier)
    if not asset_name:
        frappe.throw(_("No asset found matching '{0}'.").format(identifier))

    return get_asset_detail(asset_name)


@frappe.whitelist()
def create_complaint(asset, problem_description, work_type=None, priority=None, photo_file_url=None, requires_permit=False):
    """
    بلاغ عطل فوري — يفوِّض بالكامل لنفس create_maintenance_request
    المُستخدَمة في بوابة مدير الفرع (إنشاء + تسليم أمر عمل في استدعاء
    واحد). photo_file_url اختياري: رابط ملف مرفوع مسبقاً عبر
    /api/method/upload_file من قِبل العميل (Base64/Multipart في التطبيق
    نفسه)، يُربَط بحقل fault_photo بعد الإنشاء مباشرة.
    """
    result = create_maintenance_request(
        asset, problem_description, work_type=work_type, priority=priority, requires_permit=requires_permit
    )
    if photo_file_url:
        frappe.db.set_value(
            "Asset Work Order", result["name"], "fault_photo", photo_file_url, update_modified=False
        )
    return result


@frappe.whitelist()
def get_technician_jobs(status=None):
    """
    مهام الصيانة المفتوحة المُسنَدة للمستخدم الحالي تحديداً (فني أو
    مورِّد صيانة خارجي)، مرتبة حسب درجة خطورة الأولوية ثم موعد الاستحقاق
    — تُطبَّق طبقة الصلاحيات القياسية لـ Asset Work Order تلقائياً
    (get_list)، بالإضافة لفلتر assigned_technician الصريح هنا.

    docstatus < 2 (وليس =1 فقط) عمداً: أوامر العمل الخطرة (requires_permit
    عند الإنشاء) تبقى Draft (docstatus=0) حتى يُوقَّع تصريح عزل الطاقة —
    لو اقتصر الفلتر على docstatus=1، لن يرى الفني مهمته الخطرة المُسنَدة
    له إطلاقاً طالما هي بانتظار التوقيع، رغم أنه هو من يحتاج متابعة حالة
    التصريح والضغط على "بدء العمل" بمجرد اكتماله.
    """
    filters = {"assigned_technician": frappe.session.user, "docstatus": ["<", 2]}
    filters["status"] = status or ["not in", ["مكتمل", "ملغي", "مرفوض"]]

    return frappe.get_list(
        "Asset Work Order",
        filters=filters,
        fields=[
            "name", "title", "asset", "asset_name", "status", "priority", "work_type",
            "request_date", "resolution_due_by", "sla_breached", "problem_description", "fault_photo",
            "docstatus", "work_permit",
        ],
        order_by="field(priority, 'حرج', 'عاجل', 'متوسط', 'عادي'), resolution_due_by asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def update_job_status(
    work_order,
    action,
    reason=None,
    completion_notes=None,
    actual_cost=None,
    cost_classification=None,
    increase_in_asset_life_months=None,
):
    """
    معالجة (إتمام/رفض) أمر عمل — استدعاء واحد يُفوِّض مباشرة لنفس
    الدوال الموثَّقة والمحمية (complete_work_order/reject_work_order) في
    Asset Work Order، بما فيها كل فحوصات الصلاحية (_check_maintenance_role)
    والترحيل المحاسبي والصرف المخزني التلقائي — بلا أي منطق أعمال مكرر
    هنا.

    فحص إضافي خاص بقناة الموبايل تحديداً: _check_maintenance_role في
    Asset Work Order تسمح لأي مستخدم بدور "Asset Technician" بإتمام/رفض
    أي أمر عمل (وليس المُسنَد إليه هو تحديداً فقط) — مقصود لواجهة Desk
    (تغطية بين الفنيين). لكن قناة تطبيق الموبايل الميداني (هذا الملف) يجب
    أن تقيّد كل فني بمهامه المُسنَدة إليه هو فقط، بنفس القيد المستخدَم
    أصلاً في get_technician_jobs أعلاه — وإلا يقدر فني (من جهازه الخاص)
    إغلاق مهمة مُسنَدة لزميل آخر عبر الـ API مباشرة.

    معاملات الإتمام الإضافية (completion_notes/actual_cost/
    cost_classification/increase_in_asset_life_months) اختيارية — نفس
    الحقول بالضبط التي تُملأ بواسطة معالج سطح المكتب
    (work_order_completion_wizard) عبر frappe.client.set_value قبل
    استدعاء complete_work_order؛ تُطبَّق هنا مباشرة على المستند قبل
    استدعاء نفس الدالة، بلا تكرار منطق الإتمام نفسه.
    """
    doc = frappe.get_doc("Asset Work Order", work_order)
    is_supervisor = bool({"Asset Manager", "System Manager"} & set(frappe.get_roles()))
    if not is_supervisor and doc.assigned_technician and doc.assigned_technician != frappe.session.user:
        frappe.throw(
            _("You can only update work orders assigned to you."), frappe.PermissionError
        )

    if action == "complete":
        if completion_notes is not None:
            doc.completion_notes = completion_notes
        if actual_cost is not None:
            doc.actual_cost = actual_cost
        if cost_classification is not None:
            doc.cost_classification = cost_classification
        if increase_in_asset_life_months is not None:
            doc.increase_in_asset_life_months = increase_in_asset_life_months
        doc.complete_work_order()
    elif action == "reject":
        doc.reject_work_order(reason)
    else:
        frappe.throw(_("Unknown action '{0}'. Use 'complete' or 'reject'.").format(action))

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def submit_physical_audit(audit_id, items):
    """
    تحديث جماعي (Bulk) لبنود جرد مادي بمسودة Asset Physical Audit موجودة
    بالفعل (أُنشئت وعُبِّئت مبدئياً عبر fetch_assets)، ثم تسليمها —
    بدل إرسال كل بند بنداء API منفصل. items: قائمة
    {asset, audit_result, actual_location?, remarks?}.
    """
    if isinstance(items, str):
        items = json.loads(items)

    doc = frappe.get_doc("Asset Physical Audit", audit_id)
    if doc.docstatus != 0:
        frappe.throw(_("Audit {0} is not in draft status.").format(audit_id))

    rows_by_asset = {row.asset: row for row in doc.items}
    for item in items:
        row = rows_by_asset.get(item.get("asset"))
        if not row:
            continue
        row.audit_result = item.get("audit_result") or row.audit_result
        row.actual_location = item.get("actual_location") or row.actual_location
        row.remarks = item.get("remarks") or row.remarks

    doc.save()
    doc.submit()

    return {
        "name": doc.name,
        "audit_status": doc.audit_status,
        "found_count": doc.found_count,
        "missing_count": doc.missing_count,
        "damaged_count": doc.damaged_count,
    }
