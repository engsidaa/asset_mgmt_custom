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
from frappe.utils.password import set_encrypted_password

from asset_mgmt_custom.api.branch_manager import create_maintenance_request, get_asset_detail


@frappe.whitelist()
def generate_my_api_keys():
    """
    توليد (أو إعادة توليد) مفتاح API الخاص بالمستخدم الحالي لنفسه فقط —
    خطوة تسجيل الدخول باسم مستخدم/كلمة مرور في التطبيق (auth_repository.dart)
    تستدعي هذه الدالة عبر جلسة الكوكيز المؤقتة بعد /api/method/login
    الناجح، لتحويلها فوراً لمصادقة API Key/Secret القياسية.

    لماذا لا نستدعي frappe.core.doctype.user.user.generate_keys الأصلية
    مباشرة: تلك الدالة مقيَّدة صراحة بـ frappe.only_for("System Manager")
    (هي أصلاً إجراء إداري يُنفَّذه مسؤول من داخل نموذج User لمستخدم آخر،
    وليست ميزة "توليد مفتاحي الخاص" ذاتية الخدمة كما افتُرض خطأً عند بناء
    هذه الشاشة أول مرة) — ما كان يعني عملياً أن أي حساب فني/مدير فرع بلا
    دور System Manager يفشل تسجيل دخوله بكلمة المرور بصمت عند هذه الخطوة
    تحديداً. الحل هنا: نفس منطق الدالة الأصلية بالضبط، لكن عبر
    frappe.db.set_value (يتجاوز فحص الصلاحية العام تماماً كما في
    update_my_profile_picture أعلاه) ومُقيَّد صراحة بـ frappe.session.user
    فقط — لا يقدر أي مستخدم عبر هذا الاستدعاء توليد أو قراءة مفتاح مستخدم
    آخر مهما كانت أدواره، فلا يوجد تصعيد صلاحيات حقيقي هنا.

    يُعيد api_key وapi_secret معاً في استدعاء واحد (خلافاً للدالة
    الأصلية التي تُعيد api_secret فقط وتترك api_key ليُقرأ لاحقاً عبر
    /api/resource/User — وهو حقل بمستوى صلاحية (permlevel) أعلى مقصور
    أيضاً على System Manager، فكان سيفشل بنفس السبب حتى لو نجح التوليد).

    api_secret تحديداً حقل نوعه Password في Frappe — لا يُخزَّن في عمود
    عادي بجدول tabUser، بل مُشفَّراً في جدول __Auth منفصل عبر
    frappe.utils.password. الكتابة المباشرة بـ frappe.db.set_value (كما
    في المحاولة الأولى لهذا الإصلاح) كانت تكتب فقط عمود tabUser الخام
    بلا أثر فعلي على القيمة المُشفَّرة الحقيقية في __Auth، فيفشل تسجيل
    الدخول لاحقاً بـ AuthenticationError صامتة عند مقارنة السر المُرسَل
    بالسر المفكوك تشفيره من __Auth (frappe.auth.validate_api_key_secret)
    — رغم نجاح التوليد ورغم أن الحساب مُفعَّل. set_encrypted_password هو
    نفس المسار الذي يستخدمه doc.save() داخلياً لأي حقل Password.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Invalid or missing API credentials."), frappe.AuthenticationError)

    api_key = frappe.db.get_value("User", user, "api_key")
    if not api_key:
        api_key = frappe.generate_hash(length=15)
        frappe.db.set_value("User", user, "api_key", api_key, update_modified=False)
    api_secret = frappe.generate_hash(length=15)
    set_encrypted_password("User", user, api_secret, fieldname="api_secret")

    return {"api_key": api_key, "api_secret": api_secret}


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
        "email": frappe.db.get_value("User", user, "email"),
        "mobile_no": frappe.db.get_value("User", user, "mobile_no"),
        "roles": frappe.get_roles(user),
        "employee": employee,
        "managed_branches": managed_branches,
        "default_branch": default_branch,
    }


@frappe.whitelist()
def update_my_profile_picture(file_url):
    """
    يحدِّث صورة حساب المستخدم الحالي فقط — لا يوجد لدى الأدوار الميدانية
    (فني/مستخدم فرع/مدير فرع) أي صلاحية "write" على مستند User نفسه (مقصورة
    على System Manager في صلاحيات هذا الـ doctype الأساسية)، فمسار الحفظ
    العام (frappe.client.set_value، الذي يمر عبر doc.save() الكامل) كان
    سيفشل بصلاحية لأي مستخدم ميداني يحاول تغيير صورته الشخصية.

    db_set هنا آمن تماماً رغم تجاوزه فحص الصلاحية القياسي، لأنه مُقيَّد
    صراحة بـ frappe.session.user فقط ولا يقبل أي معرِّف مستخدم آخر — لا
    يقدر أي مستخدم عبر هذا الاستدعاء تعديل صورة غيره مهما كانت أدواره.

    الملف نفسه يُرفَع أولاً عبر /api/method/upload_file القياسي بلا
    doctype/docname (رفع عام غير مربوط) تفادياً لنفس فحص الصلاحية على
    User، ثم يُربَط هنا بالحقل الصحيح.
    """
    if not file_url:
        frappe.throw(_("file_url is required."))
    frappe.db.set_value("User", frappe.session.user, "user_image", file_url, update_modified=False)
    return {"user_image": file_url}


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
def create_complaint(
    asset=None, problem_description=None, work_type=None, priority=None, photo_file_url=None, requires_permit=False,
    complaint_department=None,
):
    """
    بلاغ عطل فوري — يفوِّض بالكامل لنفس create_maintenance_request
    المُستخدَمة في بوابة مدير الفرع (إنشاء + تسليم أمر عمل في استدعاء
    واحد). photo_file_url اختياري: رابط ملف مرفوع مسبقاً عبر
    /api/method/upload_file من قِبل العميل (Base64/Multipart في التطبيق
    نفسه)، يُربَط بحقل fault_photo بعد الإنشاء مباشرة.

    asset اختياري: شكوى عامة غير مرتبطة بأصل محدد — نفس مسار الإنشاء/
    التسليم بالضبط (انظر create_maintenance_request)، فقط بلا ربط بأصل؛
    الفرع يُستنتَج حينها من فرع المستخدم نفسه. complaint_department
    ("تقنية المعلومات"/"صيانة عامة") إجباري في هذه الحالة — يُحدِّد الجهة
    التي يجب أن تستلم الشكوى.
    """
    result = create_maintenance_request(
        asset, problem_description, work_type=work_type, priority=priority, requires_permit=requires_permit,
        complaint_department=complaint_department,
    )
    if photo_file_url:
        frappe.db.set_value(
            "Asset Work Order", result["name"], "fault_photo", photo_file_url, update_modified=False
        )
    return result


_PRIORITY_RANK = {"حرج": 4, "عاجل": 3, "متوسط": 2, "عادي": 1}


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

    الترتيب حسب الأولوية يتم في بايثون بعد الجلب، وليس عبر order_by خام
    في SQL (field(priority, 'حرج', ...)) — Frappe يرفض أي order_by يحتوي
    حرفاً خارج [a-z0-9-_ ,`'".()] برسالة "Illegal SQL Query"
    (frappe.model.db_query.ORDER_GROUP_PATTERN)، والأحرف العربية هنا
    تسقط دائماً خارج هذه المجموعة مهما حاولت تنسيقها — لا يوجد صيغة SQL
    خام صالحة تتضمن نص عربي حرفي في order_by إطلاقاً.
    """
    filters = {"assigned_technician": frappe.session.user, "docstatus": ["<", 2]}
    filters["status"] = status or ["not in", ["مكتمل", "ملغي", "مرفوض"]]

    jobs = frappe.get_list(
        "Asset Work Order",
        filters=filters,
        fields=[
            "name", "title", "asset", "asset_name", "status", "priority", "work_type",
            "request_date", "resolution_due_by", "sla_breached", "problem_description", "fault_photo",
            "docstatus", "work_permit", "creation",
        ],
        order_by="resolution_due_by asc",
        limit_page_length=0,
    )
    jobs.sort(key=lambda j: -_PRIORITY_RANK.get(j.get("priority"), 0))
    return jobs


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
    بالفعل (أُنشئت وعُبِّئت مبدئياً عبر create_physical_audit في
    branch_manager.py)، ثم تسليمها — بدل إرسال كل بند بنداء API منفصل.
    items: قائمة {asset, audit_result, actual_location?, remarks?}.

    save()/submit() بـ ignore_permissions=True عمداً بعد التحقق من ملكية
    هذا الجرد تحديداً (audited_by == المستخدم الحالي) — صلاحية الكتابة
    الأساسية على هذا الدكتايب مقصورة على أدوار معيّنة (Asset
    Technician/User/Manager) قد لا يملكها مدير الفرع الذي أنشأ الجرد أصلاً
    عبر create_physical_audit (التي تتجاوز نفس القيد لنفس السبب).
    """
    if isinstance(items, str):
        items = json.loads(items)

    doc = frappe.get_doc("Asset Physical Audit", audit_id)
    if doc.audited_by != frappe.session.user:
        frappe.throw(_("You are not the owner of this audit."), frappe.PermissionError)
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

    doc.save(ignore_permissions=True)
    doc.submit()

    return {
        "name": doc.name,
        "audit_status": doc.audit_status,
        "found_count": doc.found_count,
        "missing_count": doc.missing_count,
        "damaged_count": doc.damaged_count,
    }


@frappe.whitelist()
def get_work_order_comments(work_order):
    """
    تعليقات المتابعة على أمر عمل — عبر هذا الاستدعاء المخصص بدل REST
    العام (/api/resource/Comment) مباشرة، لأن صلاحيات doctype Comment
    الأساسية في Frappe نفسه مقصورة على System Manager/Website Manager
    فقط (core/doctype/comment/comment.json) — أي دور ميداني آخر (فني/مدير
    فرع/مسؤول صيانة) كان يحصل على PermissionError دائماً عند القراءة عبر
    REST العام، رغم أن الإضافة (add_comment القياسي) تتجاوز هذا القيد
    صراحة عبر ignore_permissions=True عند الحفظ. الصلاحية الحقيقية
    المطلوبة هنا هي قدرة المستخدم على قراءة أمر العمل نفسه (مفحوصة أدناه
    عبر check_permission، والتي تطبّق أصلاً has_permission المخصصة لـ
    Asset Work Order)، وليس أي قيد منفصل على Comment.
    """
    frappe.get_doc("Asset Work Order", work_order).check_permission()
    return frappe.get_all(
        "Comment",
        filters={"reference_doctype": "Asset Work Order", "reference_name": work_order, "comment_type": "Comment"},
        fields=["name", "content", "comment_email", "comment_by", "creation"],
        order_by="creation desc",
        ignore_permissions=True,
    )


# ---------------------------------------------------------------------------
# التنبيهات — Notification Log القياسي في Frappe (نفس الجدول الذي يُغذّي
# جرس التنبيهات في Desk)، وليس مصدر بيانات مُختلَق: أي حدث يُنشئ تنبيهاً
# لمستخدم بعينه (تكليف فني بأمر عمل، اعتماد/رفض طلب أصل...) عبر
# asset_mgmt_custom.utils.notify.notify_user يظهر هنا مباشرة لنفس
# المستخدم على تطبيق الموبايل، بحقل read الحقيقي (وليس عدّاداً مُشتقاً
# من أرقام لوحة التحكم كما كانت شاشة "التنبيهات" سابقاً).
#
# لكن Notification Log جدول عام في Frappe نفسه — يستقبل أيضاً تنبيهات لا
# علاقة لها بهذا التطبيق إطلاقاً (إشارة (@mention) في تعليق على أي مستند
# آخر بالنظام، تكليف ToDo، مشاركة مستند، نقاط طاقة...)، فتظهر مختلطة مع
# تنبيهات التطبيق نفسه لو قُرئت بلا تصفية. كل دكتايبات هذا التطبيق
# (وكل استدعاءات notify_user/enqueue_create_notification المُستخدَمة فيه،
# هنا وفي tasks.py) مُسمّاة بادئتها "Asset" دائماً بلا استثناء — فالتصفية
# بـ document_type LIKE 'Asset%' تعزل تنبيهات هذا التطبيق فقط عن أي شيء
# آخر في النظام، بلا حاجة لصيانة قائمة صريحة بكل دكتايب كلما أُضيف جديد.
# ---------------------------------------------------------------------------

_APP_NOTIFICATION_FILTERS = [["document_type", "like", "Asset%"]]


@frappe.whitelist()
def list_my_notifications(only_unread=None, limit=50):
    filters = [["for_user", "=", frappe.session.user], *_APP_NOTIFICATION_FILTERS]
    if frappe.utils.cint(only_unread):
        filters.append(["read", "=", 0])
    return frappe.get_list(
        "Notification Log",
        filters=filters,
        fields=["name", "subject", "document_type", "document_name", "read", "creation", "type"],
        order_by="creation desc",
        limit_page_length=frappe.utils.cint(limit) or 50,
        ignore_permissions=True,
    )


@frappe.whitelist()
def get_unread_notification_count():
    return frappe.db.count(
        "Notification Log",
        {"for_user": frappe.session.user, "read": 0, "document_type": ["like", "Asset%"]},
    )


@frappe.whitelist()
def mark_notification_read(name):
    """يتحقق من ملكية التنبيه (for_user) قبل التعليم كمقروء — لا صلاحية Notification Log القياسية تكفي بمفردها لمنع مستخدم من تعليم تنبيه مستخدم آخر."""
    owner = frappe.db.get_value("Notification Log", name, "for_user")
    if owner != frappe.session.user:
        frappe.throw(_("This notification does not belong to you."), frappe.PermissionError)
    frappe.db.set_value("Notification Log", name, "read", 1, update_modified=False)


@frappe.whitelist()
def mark_all_notifications_read():
    frappe.db.set_value(
        "Notification Log",
        {"for_user": frappe.session.user, "read": 0, "document_type": ["like", "Asset%"]},
        "read", 1, update_modified=False,
    )
