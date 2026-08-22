"""
Asset override
--------------
1. الأصل الاحتياطي (is_spare):
   - يُجبر على إيقاف calculate_depreciation
   - عند التفعيل (عبر سند الاستلام) يُطلب من مدير الأصول تفعيل الإهلاك

2. حالة الأصل (New / Used):
   - "Used" → تُطبَّق custom_used_depreciation_rate على جميع finance books
   - "New"  → تُستخدم نسبة الإهلاك المعيارية من Asset Category

3. كود الستيكر:
   - تحذير في حال لم يُحدَّد بعد (غير إلزامي عند الإنشاء)
"""

import frappe
from frappe import _
from frappe.utils import flt


def validate(doc, method=None):
    _enforce_spare_asset_rules(doc)
    _apply_used_depreciation_rate(doc)


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
            _(
                "Asset <b>{0}</b> is marked as a Spare asset – "
                "depreciation has been disabled automatically. "
                "It will start only after the asset is activated via an Asset Receipt."
            ).format(doc.name or doc.asset_name),
            alert=True,
            indicator="orange",
        )

    # مسح تاريخ الاستخدام لمنع احتساب إهلاك بالخطأ
    if doc.available_for_use_date:
        doc.available_for_use_date = None
        frappe.msgprint(
            _("Available for Use Date cleared because asset is marked as Spare."),
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
    if not used_rate:
        return

    if not doc.calculate_depreciation:
        return

    for row in doc.finance_books:
        if row.depreciation_method in ("Straight Line", "Written Down Value"):
            row.rate_of_depreciation = used_rate
