"""
Asset override
--------------
1. الأصل الاحتياطي (is_spare):
   - يُجبر على إيقاف calculate_depreciation
   - عند التفعيل (عبر سند الاستلام) يُطلب من مدير الأصول تفعيل الإهلاك

2. حالة الأصل (New / Used):
   - "Used" → تُطبَّق custom_used_depreciation_rate على جميع finance books
   - "New"  → تُستخدم نسبة الإهلاك المعيارية من Asset Category

3. حالتان منفصلتان (بدل حالة واحدة مدموجة):
   - custom_coding_status (Uncoded/Coded): خطوة الترميز — لصق/نقش الكود
     وتوثيقه بصورتين (قبل وبعد). تُضبط عبر mark_coded().
   - custom_operational_status (Incomplete/Operational/In Transit): التفعيل
     التشغيلي الفعلي وبدء الإهلاك. يشترط أن يكون الأصل مُرمَّزاً (Coded) أولاً.
     تُضبط عبر set_operational().

4. mark_coded() ثم set_operational(): إجراءان منفصلان بالترتيب — مسئول
   الفرع يلصق الكود ويرفع الصورتين أولاً، ثم يُفعِّل الأصل تشغيلياً لاحقاً.
"""

import frappe
from frappe import _
from frappe.utils import flt, today


def validate(doc, method=None):
    _inherit_branch_and_cost_center(doc)
    _enforce_spare_asset_rules(doc)
    _apply_used_depreciation_rate(doc)
    _auto_set_incomplete_status(doc)
    _auto_set_uncoded_status(doc)
    _auto_set_running_default(doc)


# ---------------------------------------------------------------------------
# Branch / Cost Center Inheritance (Company -> Branch -> Location -> Asset)
# ---------------------------------------------------------------------------

def _inherit_branch_and_cost_center(doc):
    """
    يفرض هرمية الوراثة الإجبارية Company -> Branch -> Location -> Asset:
    أي أصل جديد (بما فيها الأصول التي ينشئها ERPNext تلقائياً كمسودة عند
    تسليم Purchase Receipt/Purchase Invoice لصنف is_fixed_asset — انظر
    buying_controller.make_asset()، الذي يضبط location فقط ولا يعرف شيئاً
    عن custom_branch/cost_center الخاصين بهذا التطبيق) يجب أن يرث الفرع
    ومركز التكلفة تلقائياً من موقعه، دون إدخال يدوي.

    هذا ضروري تحديداً لرسملة الـ CWIP: Asset.make_gl_entries() (كود Core
    في erpnext/assets/doctype/asset/asset.py) يستخدم self.cost_center
    مباشرة في قيد تحويل رصيد "أصول تحت التنفيذ" إلى "الأصول الثابتة" عند
    تسليم الأصل — فلو تُرك فارغاً، يُفقد ربط مركز التكلفة بالفرع في هذا
    القيد المحاسبي الأهم في دورة حياة الأصل بالكامل.

    ملاحظة: لا حاجة لأي كود مخصص لتوليد قيد الرسملة نفسه — رسملة CWIP
    كاملة (تفعيل enable_cwip_accounting على Asset Category + ضبط
    capital_work_in_progress_account/fixed_asset_account على Asset
    Category Account) مبنية بالفعل في ERPNext الأساسي وتعمل تلقائياً
    عند تسليم (submit) الأصل — إعادة بنائها هنا كانت ستكرر/تصادم مع
    منطق Core مباشرة.
    """
    if not doc.location:
        return

    if not doc.get("custom_branch"):
        branch = frappe.db.get_value(
            "Branch", {"custom_default_location": doc.location}, "name"
        )
        if branch:
            doc.custom_branch = branch

    if not doc.cost_center:
        cost_center = frappe.db.get_value("Location", doc.location, "custom_cost_center")
        if not cost_center and doc.get("custom_branch"):
            cost_center = frappe.db.get_value("Branch", doc.custom_branch, "custom_cost_center")
        if cost_center:
            doc.cost_center = cost_center


def after_insert(doc, method=None):
    _set_maintenance_schedule_from_category(doc)
    _link_source_requisition(doc)


def _link_source_requisition(doc):
    """
    يُكمِل سلسلة التتبع الكاملة لرسملة الأصل من ميزانية رأسمالية:
    Asset Requisition -> Material Request -> Purchase Receipt -> Asset.

    ERPNext الأساسي (buying_controller.make_asset()) يضبط
    doc.purchase_receipt_item عند إنشاء الأصل تلقائياً من بند فعلي في
    Purchase Receipt، لكنه لا يعرف شيئاً عن Asset Requisition الخاص بهذا
    التطبيق. هنا نتتبَّع للخلف: Purchase Receipt Item -> Material Request
    (حقل قياسي) -> custom_source_asset_requisition (حقل مخصص أضفناه) ->
    Asset Requisition، ثم نربط الاتجاهين معاً.
    """
    if not doc.get("purchase_receipt_item"):
        return

    material_request = frappe.db.get_value(
        "Purchase Receipt Item", doc.purchase_receipt_item, "material_request"
    )
    if not material_request:
        return

    requisition = frappe.db.get_value(
        "Material Request", material_request, "custom_source_asset_requisition"
    )
    if not requisition:
        return

    frappe.db.set_value("Asset", doc.name, "custom_source_requisition", requisition, update_modified=False)
    if not frappe.db.get_value("Asset Requisition", requisition, "linked_asset"):
        frappe.db.set_value("Asset Requisition", requisition, "linked_asset", doc.name, update_modified=False)


def _set_maintenance_schedule_from_category(doc):
    """Auto-set next maintenance date from Asset Category default frequency."""
    if not doc.asset_category:
        return
    freq_days = frappe.db.get_value(
        "Asset Category", doc.asset_category, "custom_maintenance_frequency_days"
    )
    if not freq_days:
        return
    from frappe.utils import add_days, today
    next_date = add_days(today(), int(freq_days))
    frappe.db.set_value("Asset", doc.name, "custom_next_maintenance_date", next_date, update_modified=False)


def _auto_set_incomplete_status(doc):
    """نضمن أن الأصل الجديد يبدأ بحالة Incomplete إن لم تُضبط."""
    if not doc.custom_operational_status:
        doc.custom_operational_status = "Incomplete"


def _auto_set_uncoded_status(doc):
    """نضمن أن الأصل الجديد يبدأ بحالة ترميز Uncoded إن لم تُضبط."""
    if not doc.get("custom_coding_status"):
        doc.custom_coding_status = "Uncoded"


def _auto_set_running_default(doc):
    """نضمن أن الأصل الجديد يبدأ بحالة 'يعمل' افتراضياً إن لم تُضبط."""
    if doc.get("custom_is_running") is None:
        doc.custom_is_running = 1


# ---------------------------------------------------------------------------
# Spare Asset Rules
# ---------------------------------------------------------------------------

def _enforce_spare_asset_rules(doc):
    """
    الأصول الاحتياطية لا تُستهلك حتى يتم تفعيلها.
    يُجبر النظام على إيقاف الإهلاك عند وضع علامة 'احتياطي' — عن طريق
    calculate_depreciation=0 فقط، وهو ما يمنع احتساب أي جدول إهلاك في
    ERPNext الأساسي بغض النظر عن available_for_use_date.

    ملاحظة: نسخة سابقة من هذه الدالة كانت أيضاً تمسح available_for_use_date
    بالكامل (doc.available_for_use_date = None) بافتراض إنها خطوة إضافية
    احترازية — لكن هذا الحقل إلزامي في ERPNext الأساسي لأي أصل غير مركّب
    (composite) بغض النظر عن حالة الإهلاك، فمسحه كان يمنع تقديم (submit)
    أي أصل احتياطي نهائياً برسالة "Available for use date is required".
    مسح الحقل لم يكن ضرورياً أصلاً: calculate_depreciation=0 وحده كافٍ
    ومضمون لمنع الإهلاك.
    """
    if not doc.get("custom_is_spare"):
        return

    if doc.calculate_depreciation:
        doc.calculate_depreciation = 0
        frappe.msgprint(
            _("Asset {0} is marked as Spare – depreciation disabled.").format(
                doc.name or doc.asset_name
            ),
            alert=True,
            indicator="orange",
        )


# ---------------------------------------------------------------------------
# Used Asset Depreciation Rate
# ---------------------------------------------------------------------------

def _apply_used_depreciation_rate(doc):
    """
    لو حالة الأصل = 'Used'، تُطبَّق نسبة الإهلاك المخصصة على جميع
    finance books بدلاً من النسبة المعيارية للتصنيف.
    """
    if doc.get("custom_asset_condition") != "Used":
        return

    used_rate = flt(doc.get("custom_used_depreciation_rate"))
    if not used_rate or not doc.calculate_depreciation:
        return

    for row in doc.finance_books:
        if row.depreciation_method in ("Straight Line", "Written Down Value"):
            row.rate_of_depreciation = used_rate


# ---------------------------------------------------------------------------
# Mark Coded whitelist API (step 1: tagging/coding)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def mark_coded(asset_name):
    """
    Branch manager clicks "وضع علامة مُرمَّز" (Mark Coded) after physically
    tagging the asset. Validates: tag type + tag code + BOTH before/after
    photos present. Then sets custom_coding_status = Coded.

    This is deliberately separate from set_operational() — coding the asset
    (sticking the barcode/RFID/iron code and documenting it) and activating
    it for operational use are two distinct steps with two distinct gates.
    """
    doc = frappe.get_doc("Asset", asset_name)

    if doc.custom_coding_status == "Coded":
        frappe.throw(_("Asset is already marked as Coded."))

    if not doc.custom_tag_type:
        frappe.throw(
            _("Please set the Tag Type (Barcode / RFID / Iron Code) before coding the asset."),
            title=_("Missing Tag Type"),
        )

    if doc.custom_tag_type == "Iron Code" and not doc.custom_iron_code:
        frappe.throw(
            _("Iron Code is required for assets with tag type 'Iron Code'."),
            title=_("Missing Iron Code"),
        )

    if doc.custom_tag_type in ("Barcode", "RFID") and not doc.custom_sticker_code:
        frappe.throw(
            _("Sticker Code is required for assets with tag type '{0}'.").format(doc.custom_tag_type),
            title=_("Missing Sticker Code"),
        )

    if not doc.custom_tagging_photo_before:
        frappe.throw(
            _("A 'before' photo (taken before sticking/engraving the code) is required."),
            title=_("Missing Before Photo"),
        )

    if not doc.custom_tagging_photo:
        frappe.throw(
            _("An 'after' photo (taken after sticking/engraving the code) is required."),
            title=_("Missing After Photo"),
        )

    frappe.db.set_value(
        "Asset",
        asset_name,
        {
            "custom_coding_status": "Coded",
            "custom_tagged_by": frappe.session.user,
            "custom_tagged_on": today(),
        },
        update_modified=True,
    )

    _log_activity(asset_name, "Asset marked as Coded by {0}".format(frappe.session.user))

    return "Coded"


# ---------------------------------------------------------------------------
# Set Operational whitelist API (step 2: operational activation)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def set_operational(asset_name):
    """
    Branch manager clicks "Set Operational" after the asset has been coded.
    Requires custom_coding_status == Coded first (see mark_coded()).
    Then sets custom_operational_status = Operational and
    available_for_use_date = today — this is the exact moment ERPNext
    starts computing depreciation for the asset.
    """
    doc = frappe.get_doc("Asset", asset_name)

    if doc.custom_operational_status == "Operational":
        frappe.throw(_("Asset is already Operational."))

    if doc.custom_coding_status != "Coded":
        frappe.throw(
            _("Asset must be marked as Coded (tag + before/after photos) before it can be set Operational."),
            title=_("Asset Not Coded"),
        )

    frappe.db.set_value(
        "Asset",
        asset_name,
        {
            "custom_operational_status": "Operational",
            "custom_activation_date": today(),
            "custom_activated_by": frappe.session.user,
            "available_for_use_date": today(),
        },
        update_modified=True,
    )

    _log_activity(asset_name, "Asset set to Operational by {0}".format(frappe.session.user))

    return "Operational"


# ---------------------------------------------------------------------------
# Toggle Running/Stopped (daily on/off — distinct from Set Operational)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def toggle_asset_running(asset_name):
    """
    تبديل حالة "يعمل/متوقف" اليومية لأصل مُفعَّل تشغيلياً بالفعل — مُستقلة
    تماماً عن custom_operational_status (بوابة تفعيل تُضبط مرة واحدة فقط
    وتُشغّل بداية الإهلاك). يُستخدم من حركة سحب بطاقة الأصل يميناً بتطبيق
    الموبايل، ولا معنى لتشغيل/إيقاف أصل لم يُفعَّل تشغيلياً بعد.
    """
    doc = frappe.get_doc("Asset", asset_name)

    if doc.custom_operational_status != "Operational":
        frappe.throw(
            _("Asset must be set Operational before its running status can be toggled."),
            title=_("Asset Not Operational"),
        )

    currently_running = doc.custom_is_running != 0
    new_value = 0 if currently_running else 1

    frappe.db.set_value("Asset", asset_name, "custom_is_running", new_value, update_modified=True)

    _log_activity(
        asset_name,
        "Asset marked as {0} by {1}".format("Running" if new_value else "Stopped", frappe.session.user),
    )

    return {"custom_is_running": new_value}


# ---------------------------------------------------------------------------
# QR Code (deep-link to a pre-filled maintenance request)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_qr_code(asset_name):
    """
    يُنشئ QR Code يشفّر رابطاً يفتح مباشرة نموذج "أمر عمل" جديد مُعبّأ
    مسبقاً بهذا الأصل (Frappe يقرأ query parameters على مسار /new تلقائياً
    ويملأ بيها الحقول المطابقة — آلية موثّقة، وليست افتراضاً). المستخدم
    (موظف مطبخ مثلاً) يمسح الكود من على الجهاز، فيفتح طلب صيانة جاهز
    بدل ما يدوّر على الأصل يدوياً في القائمة.

    ملاحظة: قالب الطباعة "Asset Barcode Label" كان يشير سابقاً إلى
    frappe.utils.weasyprint.get_barcode — دالة غير موجودة إطلاقاً في هذا
    الإصدار من Frappe (تم التحقق من الكود المصدري)، أي أن صورة الـ QR في
    الملصق كانت معطوبة (رابط صورة 404) بغض النظر عن هذا التعديل. تم
    استبدالها بالملف الفعلي المُنشأ هنا.
    """
    from io import BytesIO
    from pyqrcode import create as qrcreate

    if not frappe.db.exists("Asset", asset_name):
        frappe.throw(_("Asset {0} not found.").format(asset_name))

    url = f"{frappe.utils.get_url()}/app/asset-work-order/new?asset={asset_name}"

    stream = BytesIO()
    try:
        qrcreate(url).svg(stream, scale=6, background="#ffffff", module_color="#000000")
        svg_content = stream.getvalue()
    finally:
        stream.close()

    existing = frappe.db.get_value("Asset", asset_name, "custom_qr_code")
    if existing:
        old_file = frappe.db.get_value("File", {"file_url": existing}, "name")
        if old_file:
            frappe.delete_doc("File", old_file, ignore_permissions=True, force=True)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{asset_name}-qr.svg",
        "attached_to_doctype": "Asset",
        "attached_to_name": asset_name,
        "attached_to_field": "custom_qr_code",
        "content": svg_content,
        "is_private": 0,
    })
    file_doc.save(ignore_permissions=True)

    frappe.db.set_value("Asset", asset_name, "custom_qr_code", file_doc.file_url, update_modified=False)
    return file_doc.file_url


def _log_activity(asset_name, subject):
    try:
        frappe.get_doc({
            "doctype": "Asset Activity",
            "asset": asset_name,
            "subject": subject,
            "user": frappe.session.user,
            "date": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True, ignore_links=True)
    except Exception:
        pass
