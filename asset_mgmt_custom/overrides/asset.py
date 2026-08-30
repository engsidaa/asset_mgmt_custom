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
    _enforce_spare_asset_rules(doc)
    _apply_used_depreciation_rate(doc)
    _auto_set_incomplete_status(doc)
    _auto_set_uncoded_status(doc)


def after_insert(doc, method=None):
    _set_maintenance_schedule_from_category(doc)


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
