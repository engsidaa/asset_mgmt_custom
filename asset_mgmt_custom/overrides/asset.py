"""
Asset override
--------------
عند التحقق من صحة الأصل:
  - لو حالة الأصل "مستعمل" → تُطبَّق نسبة الإهلاك الخاصة بالمستعمل
    (custom_used_depreciation_rate) على كل finance_book
"""

import frappe


def validate(doc, method=None):
    _apply_used_asset_rate(doc)


def _apply_used_asset_rate(doc):
    condition = doc.get("custom_asset_condition")
    used_rate = doc.get("custom_used_depreciation_rate")

    if condition != "Used" or not used_rate:
        return

    if not doc.calculate_depreciation:
        return

    for row in doc.finance_books:
        # نُطبَّق فقط على طريقة القسط الثابت لأنه الاستخدام المطلوب
        if row.depreciation_method in ("Straight Line", "Written Down Value"):
            row.rate_of_depreciation = used_rate
