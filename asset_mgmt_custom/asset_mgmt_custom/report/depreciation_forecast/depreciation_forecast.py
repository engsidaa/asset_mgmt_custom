import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months
from datetime import date


def execute(filters=None):
    filters = filters or {}
    forecast_years = int(filters.get("forecast_years") or 3)

    # Dynamic month columns
    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Book Value"), "fieldname": "book_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Method"), "fieldname": "depreciation_method", "fieldtype": "Data", "width": 130},
        {"label": _("Annual Depreciation"), "fieldname": "annual_depreciation", "fieldtype": "Currency", "width": 160},
    ]

    # Add one column per forecast year
    for i in range(1, forecast_years + 1):
        yr = date.today().year + i
        columns.append({
            "label": f"FY {yr} Depreciation",
            "fieldname": f"fy_{yr}",
            "fieldtype": "Currency",
            "width": 150,
        })

    conditions = "a.docstatus < 2 AND a.calculate_depreciation = 1"
    values = {}

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    assets = frappe.db.sql(
        f"""
        SELECT
            a.name,
            a.asset_name,
            a.asset_category,
            IFNULL(a.value_after_depreciation, a.gross_purchase_amount)  AS book_value,
            a.depreciation_method,
            a.gross_purchase_amount,
            a.salvage_value,
            a.total_number_of_depreciations,
            a.frequency_of_depreciation
        FROM `tabAsset` a
        WHERE {conditions}
        ORDER BY a.asset_category, a.name
        """,
        values,
        as_dict=True,
    )

    for row in assets:
        # Compute a simple straight-line annual depreciation
        depreciable = flt(row.gross_purchase_amount) - flt(row.salvage_value)
        periods = flt(row.total_number_of_depreciations) or 1
        freq = flt(row.frequency_of_depreciation) or 12
        annual_periods = 12.0 / freq
        if annual_periods == 0:
            annual_periods = 1
        annual_dep = depreciable / (periods / annual_periods) if periods else 0

        row["annual_depreciation"] = annual_dep
        remaining = flt(row.book_value)

        for i in range(1, forecast_years + 1):
            yr = date.today().year + i
            yr_dep = min(annual_dep, remaining) if remaining > 0 else 0
            row[f"fy_{yr}"] = yr_dep
            remaining = max(remaining - yr_dep, 0)

    return columns, assets
