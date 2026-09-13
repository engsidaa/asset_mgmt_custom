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
import math
from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, getdate, now_datetime, time_diff_in_hours, today
from frappe.utils.password import set_encrypted_password

from asset_mgmt_custom.api.branch_manager import create_maintenance_request, get_asset_detail
from asset_mgmt_custom.utils.it_scope import IT_DEPARTMENT_LABEL, is_it_technician, get_it_asset_categories
from asset_mgmt_custom.utils.notify import notify_user


def _require_it_technician():
    if not is_it_technician() and "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("This action is limited to IT department technicians."), frappe.PermissionError
        )


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

    # فني مُعيَّن صراحةً لجهة "تقنية المعلومات" ضمن أي فريق صيانة — نفس
    # المعيار المستخدم في التوزيع التلقائي لشكاوى IT
    # (AssetWorkOrder._auto_dispatch_technician) وتنبيهات تراخيص البرامج
    # (tasks._get_it_department_users)، مُجمَّع الآن في utils/it_scope.py.
    # يُستخدَم في العميل لإظهار عناصر خاصة بقسم IT (تراخيص البرامج،
    # تضييق نطاق الأصول/الفئات، مرحلة اعتماد إضافية في طلب الأصل) لفنيّي
    # هذا القسم فقط.
    user_is_it_technician = is_it_technician(user)

    field_verification = frappe.db.get_value(
        "Asset Mgmt Settings", None,
        ["field_verification_enabled", "field_verification_radius_meters"],
        as_dict=True,
    ) or {}

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
        "is_it_technician": user_is_it_technician,
        "field_verification_enabled": bool(field_verification.get("field_verification_enabled")),
        "field_verification_radius_meters": flt(field_verification.get("field_verification_radius_meters")) or 200,
    }


@frappe.whitelist()
def check_app_version(current_build_number=0):
    """
    فحص إصدار تطبيق الموبايل — يُقارَن رقم البناء الحالي (PackageInfo.
    buildNumber المُرسَل من العميل) برقم البناء الأحدث المسجَّل في
    Asset Mgmt Settings (يرفعه الإدمن يدوياً بعد نشر إصدار جديد فعلياً،
    ولا علاقة له بأي متجر تطبيقات — التطبيق يُوزَّع كملف APK مباشر).
    force_update لا يُرفَع كـ True إلا لو كان هناك فعلاً إصدار أحدث،
    حتى لا يمنع تطبيق محدَّث بالفعل من العمل بالخطأ لو تُرك الخيار
    مفعَّلاً من تحديث سابق.
    """
    settings = frappe.db.get_singles_dict("Asset Mgmt Settings")
    latest_build = cint(settings.get("latest_app_build_number"))
    update_available = latest_build > cint(current_build_number)

    return {
        "update_available": update_available,
        "force_update": bool(update_available and settings.get("force_update")),
        "latest_version_name": settings.get("latest_app_version_name"),
        "latest_build_number": latest_build,
        "download_url": settings.get("app_download_url"),
        "release_notes": settings.get("app_release_notes"),
    }


@frappe.whitelist()
def register_fcm_token(token):
    """
    يُسجَّل مرة عند بدء التطبيق (وعند أي تحديث لاحق لرمز الجهاز من
    Firebase — onTokenRefresh) ليعرف الخادم أي جهاز يخص هذا المستخدم عند
    إرسال تنبيه Push حقيقي (انظر utils/fcm.py). مُقيَّد صراحة بحساب
    المستخدم الحالي فقط — نفس نمط update_my_profile_picture أعلاه؛ لا
    صلاحية "write" عامة على User مطلوبة لمجرد تحديث رمز جهاز المستخدم
    نفسه (مقصورة أصلاً على System Manager في صلاحيات هذا الدكتايب).

    جهاز واحد نشط لكل مستخدم عمداً (يستبدل القيمة القديمة بالكامل) — هذا
    التطبيق مصمَّم لجهاز ميداني واحد لكل فني/مستخدم، وليس عدة أجهزة معاً.
    """
    if not token:
        frappe.throw(_("token is required."))
    frappe.db.set_value("User", frappe.session.user, "custom_fcm_token", token, update_modified=False)


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

    فني تقنية المعلومات مُقيَّد هنا أيضاً على فئات/أصول قسمه فقط (نفس
    القيد المُطبَّق في list_my_assets — انظر utils/it_scope.py) — لا معنى
    لعرض ثلاجات/مكيفات الفرع لفني IT موفَد لإصلاح جهاز كمبيوتر فيه.
    """
    filters = {
        "custom_branch": branch,
        "docstatus": 1,
        "status": ["not in", ["Scrapped", "Sold"]],
    }
    if is_it_technician():
        it_categories = get_it_asset_categories()
        filters["asset_category"] = ["in", it_categories or ["__none__"]]

    return frappe.get_list(
        "Asset",
        filters=filters,
        fields=[
            "name", "asset_name", "asset_category", "location", "status",
            "custom_operational_status", "custom_is_running", "custom_coding_status", "image",
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


def _haversine_meters(lat1, lng1, lat2, lng2):
    """المسافة الدائرية بين نقطتين (متر) — صيغة Haversine القياسية، بلا
    أي مكتبة خارجية (كل ما نحتاجه حساب تقريبي بدقة كافية لمقارنة نصف
    قطر بالأمتار، وليس ملاحة دقيقة)."""
    earth_radius_m = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


@frappe.whitelist()
def verify_field_location(work_order, latitude=None, longitude=None, rescanned_identifier=None):
    """
    EAM-2: تحقق ميداني اختياري (Asset Mgmt Settings.field_verification_enabled)
    قبل إتمام أمر عمل — يُقارن موقع الفني الحالي (GPS من الجهاز) بموقع
    الأصل المسجَّل (Asset.location -> Location.latitude/longitude، حقلا
    core جاهزان بالفعل، بلا أي حقل جديد على الأصل نفسه)، ويتحقق اختيارياً
    من تطابق كود مُعاد مسحه (QR/باركود) مع نفس الأصل عبر
    resolve_asset_identifier الموجودة أصلاً.

    **هذا تسجيل للتدقيق فقط — لا يمنع الإتمام مطلقاً** مهما كانت
    النتيجة (Out of Range/Asset Mismatch)؛ القرار النهائي يبقى للفني،
    وأي حالة مشبوهة تظهر لاحقاً بوضوح على أمر العمل نفسه لمسؤول الصيانة
    (انظر الوصف الكامل على Asset Mgmt Settings.field_verification_enabled).
    """
    if not frappe.db.get_single_value("Asset Mgmt Settings", "field_verification_enabled"):
        frappe.throw(_("Field verification is not enabled in Asset Mgmt Settings."))

    doc = frappe.get_doc("Asset Work Order", work_order)
    is_supervisor = bool({"Asset Manager", "System Manager"} & set(frappe.get_roles()))
    if not is_supervisor and doc.assigned_technician and doc.assigned_technician != frappe.session.user:
        frappe.throw(_("You can only verify work orders assigned to you."), frappe.PermissionError)

    distance = None
    status = "Not Attempted"

    if doc.asset and latitude and longitude:
        location = frappe.db.get_value("Asset", doc.asset, "location")
        loc_lat, loc_lng = (None, None)
        if location:
            loc_lat, loc_lng = frappe.db.get_value("Location", location, ["latitude", "longitude"]) or (None, None)
        if loc_lat and loc_lng:
            distance = round(_haversine_meters(flt(latitude), flt(longitude), flt(loc_lat), flt(loc_lng)), 1)
            radius = flt(frappe.db.get_single_value("Asset Mgmt Settings", "field_verification_radius_meters")) or 200
            status = "Verified" if distance <= radius else "Out of Range"

    if rescanned_identifier:
        matched_asset = resolve_asset_identifier(rescanned_identifier)
        if not matched_asset or matched_asset != doc.asset:
            status = "Asset Mismatch"

    frappe.db.set_value(
        "Asset Work Order", work_order,
        {
            "field_verification_status": status,
            "field_verification_distance_meters": distance,
            "field_verified_at": now_datetime(),
        },
        update_modified=False,
    )
    return {"status": status, "distance_meters": distance}


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
    complaint_department=None, it_device_type=None, it_full_outage=False,
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
    التي يجب أن تستلم الشكوى. it_device_type/it_full_outage: خاصان
    بشكوى تقنية المعلومات فقط (نوع الجهاز، وهل تعطيل كامل يستحق مهلة
    استجابة أسرع — انظر AssetWorkOrder._apply_sla_policy)، يُتجاهَلان
    بصمت لأي شكوى أخرى.
    """
    result = create_maintenance_request(
        asset, problem_description, work_type=work_type, priority=priority, requires_permit=requires_permit,
        complaint_department=complaint_department, it_device_type=it_device_type, it_full_outage=it_full_outage,
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
            "docstatus", "work_permit", "creation", "complaint_department", "it_device_type", "it_full_outage",
        ],
        order_by="resolution_due_by asc",
        limit_page_length=0,
    )
    jobs.sort(key=lambda j: -_PRIORITY_RANK.get(j.get("priority"), 0))
    return jobs


@frappe.whitelist()
def list_software_licenses(only_expiring=False):
    """
    تراخيص البرامج (Asset Software License) — خاصة بفنيّي تقنية المعلومات
    تحديداً (انظر is_it_technician في get_app_context، مُستخدَمة في
    العميل لإظهار هذه الشاشة أصلاً)، ليست وظيفة عامة لكل فني. تعتمد
    بالكامل على صلاحية القراءة القياسية الممنوحة فعلاً لدور Asset
    Technician على هذا الدكتايب (frappe.get_list تُطبِّقها تلقائياً)،
    بلا أي تقييد إضافي هنا.

    only_expiring: يُرجِع فقط التراخيص المنتهية أو المقتربة من الانتهاء
    خلال 30 يوماً القادمة — لعرض مختصر في الشاشة الرئيسية بدل القائمة
    الكاملة.
    """
    filters = {}
    if frappe.utils.cint(only_expiring):
        filters["expiry_date"] = ["<=", frappe.utils.add_days(frappe.utils.today(), 30)]
        filters["status"] = ["not in", ["Terminated"]]

    return frappe.get_list(
        "Asset Software License",
        filters=filters,
        fields=[
            "name", "software_name", "vendor", "license_type", "license_key",
            "asset", "asset_name", "purchase_date", "expiry_date",
            "total_seats", "used_seats", "annual_cost", "status", "renewal_reminder_days", "notes",
        ],
        order_by="expiry_date asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def create_software_license(
    software_name, license_type=None, asset=None, vendor=None, license_key=None,
    purchase_date=None, expiry_date=None, total_seats=None, used_seats=None,
    annual_cost=None, notes=None,
):
    """
    إنشاء ترخيص برنامج جديد من تطبيق الموبايل — مقصور على فنيّي تقنية
    المعلومات (صلاحية الكتابة الأساسية على Asset Software License مقصورة
    على System/Asset/Finance Manager؛ Asset Technician للقراءة فقط —
    انظر permissions في الدكتايب نفسه)، فـ insert(ignore_permissions=True)
    هنا يتجاوز ذلك عمداً بعد التحقق الصريح أعلاه من _require_it_technician.
    """
    _require_it_technician()
    if not software_name or not str(software_name).strip():
        frappe.throw(_("Software name is required."))

    doc = frappe.new_doc("Asset Software License")
    doc.software_name = software_name
    doc.license_type = license_type or None
    doc.asset = asset or None
    doc.vendor = vendor or None
    doc.license_key = license_key or None
    doc.purchase_date = purchase_date or None
    doc.expiry_date = expiry_date or None
    doc.total_seats = frappe.utils.cint(total_seats) if total_seats else None
    doc.used_seats = frappe.utils.cint(used_seats) if used_seats else None
    doc.annual_cost = frappe.utils.flt(annual_cost) if annual_cost else None
    doc.notes = notes or None
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist()
def update_software_license(
    name, software_name=None, license_type=None, asset=None, vendor=None, license_key=None,
    purchase_date=None, expiry_date=None, total_seats=None, used_seats=None,
    annual_cost=None, notes=None, status=None,
):
    """
    تعديل ترخيص موجود — نفس نمط الكتابة المباشرة (db.set_value) المُتَّبَع
    في بقية هذا الملف بدل doc.save() الكامل: فقط الحقول المُرسَلة فعلياً
    (غير None) تُحدَّث، وaudit التعديل يبقى في Version تلقائياً من Frappe.
    """
    _require_it_technician()
    if not frappe.db.exists("Asset Software License", name):
        frappe.throw(_("Software License {0} not found.").format(name))

    values = {
        k: v for k, v in {
            "software_name": software_name, "license_type": license_type, "asset": asset,
            "vendor": vendor, "license_key": license_key, "purchase_date": purchase_date,
            "expiry_date": expiry_date,
            "total_seats": frappe.utils.cint(total_seats) if total_seats is not None else None,
            "used_seats": frappe.utils.cint(used_seats) if used_seats is not None else None,
            "annual_cost": frappe.utils.flt(annual_cost) if annual_cost is not None else None,
            "notes": notes, "status": status,
        }.items() if v is not None
    }
    if not values:
        return {"name": name}

    frappe.db.set_value("Asset Software License", name, values, update_modified=True)
    return {"name": name}


@frappe.whitelist()
def request_license_renewal(name, note=None):
    """
    طلب تجديد ترخيص — فني تقنية المعلومات لا يملك صلاحية اعتماد شراء
    التجديد نفسه (مسألة مالية)، فهذا الاستدعاء لا يُجدِّد الترخيص فعلياً؛
    فقط يُنبِّه (Notification Log + Push حقيقي عبر notify_user) مدراء
    الأصول والشؤون المالية، ويُسجِّل الطلب في حقل الملاحظات كأثر واضح.
    """
    _require_it_technician()
    if not frappe.db.exists("Asset Software License", name):
        frappe.throw(_("Software License {0} not found.").format(name))

    software_name = frappe.db.get_value("Asset Software License", name, "software_name")
    subject = _("طلب تجديد ترخيص برنامج: {0} ({1})").format(software_name or name, name)
    if note:
        subject += " — " + note

    recipients = set(frappe.get_all(
        "Has Role",
        filters={"role": ["in", ["Asset Manager", "Asset Finance Manager"]], "parenttype": "User"},
        pluck="parent",
    ))
    for user in recipients:
        notify_user(user, subject, reference_doctype="Asset Software License", reference_name=name)

    existing_notes = frappe.db.get_value("Asset Software License", name, "notes") or ""
    log_line = _("[{0}] طلب تجديد من {1}: {2}").format(
        frappe.utils.now(), frappe.session.user, note or "-"
    )
    frappe.db.set_value(
        "Asset Software License", name, "notes",
        (existing_notes + "\n" + log_line).strip(),
        update_modified=False,
    )
    return {"ok": 1, "notified": len(recipients)}


@frappe.whitelist()
def update_job_status(
    work_order,
    action,
    reason=None,
    completion_notes=None,
    actual_cost=None,
    cost_classification=None,
    increase_in_asset_life_months=None,
    problem_code=None,
    cause_code=None,
    remedy_code=None,
    root_cause_notes=None,
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
        # EAM-3: تصنيف ISO 14224 اختياري — انظر AssetWorkOrder._create_failure_analysis
        if problem_code:
            doc.problem_code = problem_code
        if cause_code:
            doc.cause_code = cause_code
        if remedy_code:
            doc.remedy_code = remedy_code
        if root_cause_notes:
            doc.root_cause_notes = root_cause_notes
        doc.complete_work_order()
    elif action == "reject":
        doc.reject_work_order(reason)
    else:
        frappe.throw(_("Unknown action '{0}'. Use 'complete' or 'reject'.").format(action))

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_pcr_options():
    """
    EAM-3: قوائم رموز ISO 14224 (Problem/Cause/Remedy Codes) — تُقرَأ من
    تعريف حقول Asset Work Order نفسها (مصدر الحقيقة الوحيد، نفس القيم
    المستخدَمة فعلياً في Asset Failure Analysis) بدل تكرارها حرفياً في
    كود العميل، فلا يمكن أن تختلف القائمتان لاحقاً بمرور الوقت.
    """
    meta = frappe.get_meta("Asset Work Order")

    def _options(fieldname):
        field = meta.get_field(fieldname)
        return [o for o in (field.options or "").split("\n") if o] if field else []

    return {
        "problem_codes": _options("problem_code"),
        "cause_codes": _options("cause_code"),
        "remedy_codes": _options("remedy_code"),
    }


@frappe.whitelist()
def suggest_diagnosis(asset, problem_code):
    """
    EAM-3: مساعد تشخيص — بلا أي "ذكاء اصطناعي" فعلي، فقط تكرار أنماط
    الأعطال المسجَّلة فعلاً (Asset Failure Analysis) على نفس فئة الأصل
    لنفس رمز المشكلة، مرتَّبة بالأكثر تكراراً. يفيد الفني الجديد بمعرفة
    "غالباً هذا هو السبب/الحل هنا" مبنية على تاريخ هذا الفرع/المنشأة
    الفعلي، لا افتراضات عامة.
    """
    if not asset or not problem_code:
        return []

    asset_category = frappe.db.get_value("Asset", asset, "asset_category")
    if not asset_category:
        return []

    return frappe.db.sql(
        """
        SELECT fa.failure_mode AS cause_code, fa.remedy_code, COUNT(*) AS occurrences
        FROM `tabAsset Failure Analysis` fa
        JOIN `tabAsset` a ON a.name = fa.asset
        WHERE a.asset_category = %(asset_category)s
          AND fa.problem_code = %(problem_code)s
        GROUP BY fa.failure_mode, fa.remedy_code
        ORDER BY occurrences DESC
        LIMIT 5
        """,
        {"asset_category": asset_category, "problem_code": problem_code},
        as_dict=True,
    )


@frappe.whitelist()
def get_my_statistics():
    """
    حزمة إحصائيات احترافية واحدة لشاشة "الإحصائيات" في تطبيق الموبايل —
    محتواها يختلف حسب دور المستدعي فعلياً، بلا استدعاءات منفصلة يحتاجها
    العميل لكل قسم؛ حساب يحمل أكثر من دور يحصل على أكثر من قسم معاً:

      - "technician": فني/مورِّد صيانة — أداء شخصي بحت (assigned_technician
        = المستخدم الحالي فقط، نفس فلتر get_technician_jobs بالضبط).
      - "branch": مدير فرع/مسؤول صيانة — على مستوى ما يراه هذا المستخدم
        فعلياً؛ مُقيَّد تلقائياً بفرع مدير الفرع عبر User Permission
        القياسي في frappe.get_list (نفس آلية get_dashboard_summary)،
        بلا فلتر فرع صريح هنا.
      - "it": فني تقنية معلومات — مؤشرات إضافية خاصة بقسمه فقط.

    الحساب كله في بايثون بعد الجلب عبر get_list (وليس SQL خام) عمداً —
    حتى تُطبَّق طبقة الصلاحيات القياسية لكل doctype تلقائياً بلا تكرارها
    يدوياً هنا.
    """
    roles = set(frappe.get_roles())
    result = {}

    if roles & {"Asset Technician", "Maintenance Vendor"}:
        result["technician"] = _get_technician_statistics()

    if roles & {"Branch Manager", "Asset Manager", "System Manager"}:
        result["branch"] = _get_branch_statistics()

    if is_it_technician():
        result["it"] = _get_it_statistics()

    return result


def _work_order_performance_fields():
    return [
        "status", "creation", "closed_at", "sla_breached", "actual_cost", "labor_cost",
        "is_preventive_maintenance", "completion_date", "asset", "asset_name",
    ]


def _summarize_work_orders(rows, month_start):
    completed = [r for r in rows if r.status == "مكتمل"]
    completed_this_month = [
        r for r in completed if r.completion_date and getdate(r.completion_date) >= getdate(month_start)
    ]
    resolution_hours = [
        time_diff_in_hours(r.closed_at, r.creation) for r in completed if r.closed_at
    ]
    breached = sum(1 for r in completed if r.sla_breached)
    cost_this_month = sum(flt(r.actual_cost) or flt(r.labor_cost) for r in completed_this_month)

    return {
        "total": len(rows),
        "completed_total": len(completed),
        "completed_this_month": len(completed_this_month),
        "open": len([r for r in rows if r.status not in ("مكتمل", "ملغي", "مرفوض")]),
        "avg_resolution_hours": round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else 0,
        "sla_breach_rate_pct": round((breached / len(completed)) * 100, 1) if completed else 0,
        "cost_this_month": cost_this_month,
    }


def _get_technician_statistics():
    rows = frappe.get_list(
        "Asset Work Order",
        filters={"assigned_technician": frappe.session.user, "docstatus": 1},
        fields=_work_order_performance_fields(),
    )
    summary = _summarize_work_orders(rows, get_first_day(today()))
    completed = [r for r in rows if r.status == "مكتمل"]
    summary["preventive_count"] = sum(1 for r in completed if r.get("is_preventive_maintenance"))
    summary["corrective_count"] = len(completed) - summary["preventive_count"]
    return summary


def _get_branch_statistics():
    rows = frappe.get_list(
        "Asset Work Order",
        filters={"docstatus": 1},
        fields=_work_order_performance_fields(),
    )
    summary = _summarize_work_orders(rows, get_first_day(today()))

    # أكثر 5 أصول تكراراً في طلبات الصيانة — مرشَّح أول لفحص أعمق (عطل
    # متكرر بدل عطل عشوائي)، وليس مجرد رقم إجمالي عام.
    counter = Counter(r.asset_name or r.asset for r in rows if r.asset)
    summary["top_problem_assets"] = [{"asset": a, "count": c} for a, c in counter.most_common(5)]

    summary["total_assets"] = len(frappe.get_list("Asset", filters={"docstatus": 1}, pluck="name"))
    summary["operational_assets"] = len(frappe.get_list(
        "Asset", filters={"docstatus": 1, "custom_operational_status": "Operational"}, pluck="name"
    ))
    return summary


def _get_it_statistics():
    """
    complaint_department يُملأ فقط لشكوى عامة بلا أصل (انظر
    AssetWorkOrder._validate_general_complaint_department) — أوامر عمل
    IT المرتبطة فعلياً بأصل تُصنَّف بدلاً من ذلك عبر فئة الأصل نفسها
    (Asset Category.custom_complaint_department، انظر it_scope). عدد
    شكاوى IT المفتوحة الحقيقي = مجموع الحالتين معاً.
    """
    open_status_filter = ["not in", ["مكتمل", "ملغي", "مرفوض"]]

    general_open = len(frappe.get_list(
        "Asset Work Order",
        filters={"docstatus": 1, "complaint_department": IT_DEPARTMENT_LABEL, "status": open_status_filter},
        pluck="name",
    ))

    asset_linked_open = 0
    it_categories = get_it_asset_categories()
    if it_categories:
        it_assets = frappe.get_all(
            "Asset", filters={"asset_category": ["in", it_categories], "docstatus": 1}, pluck="name"
        )
        if it_assets:
            asset_linked_open = len(frappe.get_list(
                "Asset Work Order",
                filters={"docstatus": 1, "asset": ["in", it_assets], "status": open_status_filter},
                pluck="name",
            ))

    return {
        "licenses_expiring_30d": len(frappe.get_list(
            "Asset Software License",
            filters={"expiry_date": ["<=", add_days(today(), 30)], "status": ["not in", ["Terminated"]]},
            pluck="name",
        )),
        "it_complaints_open": general_open + asset_linked_open,
    }


@frappe.whitelist()
def get_my_van_stock():
    """
    EAM-4: مخزون عربة الفني — قطع الغيار المتوفرة فعلياً (عبر Bin
    الأساسي في ERPNext، وليس Asset Spare Part.quantity اليدوي) في
    المستودع الشخصي المُعرَّف على سجل Maintenance Team Member الخاص
    بالمستخدم الحالي (custom_van_stock_warehouse). اختياري بالكامل —
    warehouse يعود None لو لم يُحدَّد له مستودع أصلاً (لا خطأ).
    """
    warehouse = frappe.db.get_value(
        "Maintenance Team Member", {"team_member": frappe.session.user}, "custom_van_stock_warehouse"
    )
    if not warehouse:
        return {"warehouse": None, "items": []}

    spare_parts = frappe.get_list(
        "Asset Spare Part",
        filters={"item_code": ["is", "set"]},
        fields=["name", "item_name", "item_code", "unit"],
    )
    if not spare_parts:
        return {"warehouse": warehouse, "items": []}

    item_codes = [p.item_code for p in spare_parts]
    bins = frappe.get_all(
        "Bin",
        filters={"warehouse": warehouse, "item_code": ["in", item_codes]},
        fields=["item_code", "actual_qty"],
    )
    qty_by_item = {b.item_code: flt(b.actual_qty) for b in bins}

    items = [
        {
            "spare_part": p.name,
            "item_name": p.item_name,
            "unit": p.unit,
            "qty": qty_by_item.get(p.item_code, 0),
        }
        for p in spare_parts
        if qty_by_item.get(p.item_code, 0) > 0
    ]
    items.sort(key=lambda x: x["item_name"] or "")
    return {"warehouse": warehouse, "items": items}


@frappe.whitelist()
def submit_physical_audit(audit_id, items):
    """
    تحديث جماعي (Bulk) لبنود جرد مادي بمسودة Asset Physical Audit موجودة
    بالفعل (أُنشئت وعُبِّئت مبدئياً عبر create_physical_audit في
    branch_manager.py)، ثم تسليمها — بدل إرسال كل بند بنداء API منفصل.
    items: قائمة {asset, audit_result, actual_location?, remarks?, photo?}.
    photo إلزامية فعلياً (Asset Physical Audit.validate) لأي بند بنتيجة
    'مفقود' أو 'تالف' — انظر AssetPhysicalAudit._require_photo_on_missing_or_damaged.

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
        row.photo = item.get("photo") or row.photo

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
