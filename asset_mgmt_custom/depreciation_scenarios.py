"""
أداة مقارنة سيناريوهات الإهلاك (Depreciation Scenario Comparison)
--------------------------------------------------------------------
محاكاة جدول إهلاك بديل (طريقة/معدل/عمر إنتاجي مختلف) لأصل موجود فعلاً،
دون أي تعديل حقيقي على Asset Finance Book أو إنشاء Asset Depreciation
Schedule فعلي — تُستخدَم فقط نسخة في الذاكرة (frappe.get_doc + frappe.
new_doc، بلا أي .save()/.submit()) لإعادة استخدام محرك حساب الإهلاك
الأصلي في ERPNext core (AssetDepreciationSchedule.make_depr_schedule +
set_accumulated_depreciation) حرفياً — بدل إعادة كتابة معادلات القسط
الثابت/القسط المتناقص يدوياً هنا، وهو ما كان سيُخاطر بنتائج مختلفة عن
الحسابات الفعلية المُستخدَمة عند الترحيل المحاسبي الحقيقي.

الأصل نفسه (asset_doc) يُحمَّل بنسخة طازجة منفصلة عبر frappe.get_doc في
كل استدعاء ولا يُحفَظ أبداً — أي تعديل يُجريه core داخلياً على هذه
النسخة (مثال: validate_asset_finance_books قد تُصفِّر opening_accumulated
_depreciation) يبقى محلياً في الذاكرة فقط ولا يمَسّ قاعدة البيانات.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

DEPRECIATION_METHODS = ("Straight Line", "Written Down Value", "Double Declining Balance", "Manual")


def _simulate_one_scenario(asset_doc, scenario):
    depreciation_method = scenario.get("depreciation_method")
    if depreciation_method not in DEPRECIATION_METHODS:
        frappe.throw(_("Unknown depreciation method '{0}'.").format(depreciation_method))

    row = frappe._dict({
        "idx": 1,
        "finance_book": None,
        "depreciation_method": depreciation_method,
        "total_number_of_depreciations": cint(scenario.get("total_number_of_depreciations")),
        "frequency_of_depreciation": cint(scenario.get("frequency_of_depreciation") or 12),
        "rate_of_depreciation": flt(scenario.get("rate_of_depreciation")),
        "expected_value_after_useful_life": flt(scenario.get("expected_value_after_useful_life")),
        "depreciation_start_date": (
            getdate(scenario.get("depreciation_start_date")) if scenario.get("depreciation_start_date") else None
        ),
        "daily_prorata_based": 0,
        "shift_based": 0,
        "value_after_depreciation": None,
    })

    schedule_doc = frappe.new_doc("Asset Depreciation Schedule")
    schedule_doc.set_draft_asset_depr_schedule_details(asset_doc, row)
    schedule_doc.make_depr_schedule(asset_doc, row, update_asset_finance_book_row=False)
    schedule_doc.set_accumulated_depreciation(asset_doc, row)

    schedule = [
        {
            "schedule_date": s.schedule_date,
            "depreciation_amount": flt(s.depreciation_amount, 2),
            "accumulated_depreciation_amount": flt(s.accumulated_depreciation_amount, 2),
        }
        for s in schedule_doc.get("depreciation_schedule")
    ]
    total_depreciation = sum(s["depreciation_amount"] for s in schedule)
    final_book_value = flt(asset_doc.gross_purchase_amount, 2) - flt(
        schedule[-1]["accumulated_depreciation_amount"] if schedule else 0, 2
    )

    return {
        "label": scenario.get("label") or depreciation_method,
        "depreciation_method": depreciation_method,
        "number_of_periods": len(schedule),
        "total_depreciation": flt(total_depreciation, 2),
        "final_book_value": final_book_value,
        "schedule": schedule,
    }


@frappe.whitelist()
def compare_scenarios(asset, scenarios):
    """
    asset: اسم الأصل الحقيقي (للحصول على gross_purchase_amount وتاريخ
    الاستخدام الفعلي — بلا تعديل عليه إطلاقاً).
    scenarios: قائمة JSON بكل سيناريو مقترح (بلا علاقة بـ Asset Finance
    Book الفعلي للأصل) — كل عنصر: label, depreciation_method,
    total_number_of_depreciations, frequency_of_depreciation,
    expected_value_after_useful_life, rate_of_depreciation (لـ WDV/DD),
    depreciation_start_date (اختياري — الافتراضي: نهاية شهر تاريخ بدء
    استخدام الأصل الفعلي).
    """
    if isinstance(scenarios, str):
        scenarios = frappe.parse_json(scenarios)
    if not scenarios:
        frappe.throw(_("Please add at least one scenario to compare."))

    asset_doc = frappe.get_doc("Asset", asset)
    if not asset_doc.available_for_use_date:
        frappe.throw(_("Asset {0} has no 'Available For Use Date' set — cannot simulate a schedule.").format(asset))

    return {
        "asset": asset_doc.name,
        "asset_name": asset_doc.asset_name,
        "gross_purchase_amount": asset_doc.gross_purchase_amount,
        "scenarios": [_simulate_one_scenario(asset_doc, s) for s in scenarios],
    }
