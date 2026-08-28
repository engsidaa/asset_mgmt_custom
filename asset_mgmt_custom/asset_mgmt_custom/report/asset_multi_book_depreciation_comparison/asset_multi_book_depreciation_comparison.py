import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 170},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("Finance Book"), "fieldname": "finance_book", "fieldtype": "Link", "options": "Finance Book", "width": 130},
        {"label": _("Default Book?"), "fieldname": "is_default", "fieldtype": "Check", "width": 90},
        {"label": _("Method"), "fieldname": "depreciation_method", "fieldtype": "Data", "width": 140},
        {"label": _("Rate %"), "fieldname": "rate_of_depreciation", "fieldtype": "Percent", "width": 90},
        {"label": _("Purchase Value"), "fieldname": "gross_purchase_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Book Value"), "fieldname": "value_after_depreciation", "fieldtype": "Currency", "width": 130},
        {"label": _("Expected Value After Useful Life"), "fieldname": "expected_value_after_useful_life", "fieldtype": "Currency", "width": 160},
        {"label": _("Total Periods"), "fieldname": "total_number_of_depreciations", "fieldtype": "Int", "width": 100},
        {"label": _("Booked Periods"), "fieldname": "total_number_of_booked_depreciations", "fieldtype": "Int", "width": 110},
        {"label": _("Frequency (Months)"), "fieldname": "frequency_of_depreciation", "fieldtype": "Int", "width": 130},
    ]


def get_data(filters):
    conditions = "a.docstatus < 2 AND a.calculate_depreciation = 1"
    values = {}
    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]
    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    rows = frappe.db.sql(
        f"""
        SELECT
            a.name AS asset,
            a.asset_name,
            a.asset_category,
            a.gross_purchase_amount,
            a.default_finance_book,
            fb.finance_book,
            fb.depreciation_method,
            fb.rate_of_depreciation,
            fb.value_after_depreciation,
            fb.expected_value_after_useful_life,
            fb.total_number_of_depreciations,
            fb.total_number_of_booked_depreciations,
            fb.frequency_of_depreciation
        FROM `tabAsset` a
        JOIN `tabAsset Finance Book` fb ON fb.parent = a.name
        WHERE {conditions}
        ORDER BY a.name, fb.idx
        """,
        values,
        as_dict=True,
    )

    if filters.get("only_multi_book"):
        book_counts = {}
        for r in rows:
            book_counts[r.asset] = book_counts.get(r.asset, 0) + 1
        rows = [r for r in rows if book_counts.get(r.asset, 0) > 1]

    for r in rows:
        r["is_default"] = 1 if r.finance_book == r.default_finance_book else 0

    return rows
