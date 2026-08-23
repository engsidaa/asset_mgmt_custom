"""
Asset override
--------------
1. الأصل الاحتياطي (is_spare):
   - يُجبر على إيقاف calculate_depreciation
   - عند التفعيل (عبر سند الاستلام) يُطلب من مدير الأصول تفعيل الإهلاك

2. حالة الأصل (New / Used):
   - "Used" → تُطبَّق custom_used_depreciation_rate على جميع finance books
   - "New"  → تُستخدم نسبة الإهلاك المعيارية من Asset Category

3. الحالة التشغيلية:
   - الأصل الجديد يبدأ بـ Incomplete تلقائياً
   - "Set Operational" API: تحقق من tag + صورة ثم يُفعِّل الأصل

4. set_operational whitelist:
   - Branch manager clicks "Set Operational" after tagging
"""

import frappe
from frappe import _
from frappe.utils import flt, today


def validate(doc, method=None):
    _enforce_spare_asset_rules(doc)
    _apply_used_depreciation_rate(doc)
    _auto_set_incomplete_status(doc)


def _auto_set_incomplete_status(doc):
    """نضمن أن الأصل الجديد يبدأ بحالة Incomplete إن لم تُضبط."""
    if not doc.custom_operational_status:
        doc.custom_operational_status = "Incomplete"


# ---------------------------------------------------------------------------
# Spare Asset Rules
# ---------------------------------------------------------------------------

def _enforce_spare_asset_rules(doc):
    """
    الأصول الاحتياطية لا تُستهلك حتى يتم تفعيلها.
    يُجبر النظام على إيقاف الإهلاك عند وضع علامة 'احتياطي'.
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

    # مسح تاريخ الاستخدام لمنع احتساب إهلاك بالخطأ
    if doc.available_for_use_date:
        doc.available_for_use_date = None
        frappe.msgprint(
            _("Available for Use Date cleared because asset is Spare."),
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
# Set Operational whitelist API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def set_operational(asset_name):
    """
    Branch manager clicks "Set Operational" after tagging.
    Validates: tag type set + tag code present + tagging photo present.
    Then sets custom_operational_status = Operational and available_for_use_date = today.
    """
    doc = frappe.get_doc("Asset", asset_name)

    if doc.custom_operational_status == "Operational":
        frappe.throw(_("Asset is already Operational."))

    if not doc.custom_tag_type:
        frappe.throw(
            _("Please set the Tag Type (Barcode / RFID / Iron Code) before activating the asset."),
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

    if not doc.custom_tagging_photo:
        frappe.throw(
            _("A tagging photo is required before setting the asset to Operational."),
            title=_("Missing Tagging Photo"),
        )

    frappe.db.set_value(
        "Asset",
        asset_name,
        {
            "custom_operational_status": "Operational",
            "custom_activation_date": today(),
            "custom_activated_by": frappe.session.user,
            "custom_tagged_by": frappe.session.user,
            "custom_tagged_on": today(),
            "available_for_use_date": today(),
        },
        update_modified=True,
    )

    # Log activity
    try:
        frappe.get_doc({
            "doctype": "Asset Activity",
            "asset": asset_name,
            "subject": "Asset set to Operational by {0}".format(frappe.session.user),
            "user": frappe.session.user,
            "date": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True, ignore_links=True)
    except Exception:
        pass

    return "Operational"
