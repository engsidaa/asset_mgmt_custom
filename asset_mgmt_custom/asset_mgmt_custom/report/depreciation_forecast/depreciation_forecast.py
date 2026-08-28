import frappe
from frappe import _
from frappe.utils import flt, getdate
from datetime import date
from collections import defaultdict


def execute(filters=None):
    filters = filters or {}
    forecast_years = int(filters.get("forecast_years") or 3)

    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 170},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("Finance Book"), "fieldname": "finance_book", "fieldtype": "Link", "options": "Finance Book", "width": 130},
        {"label": _("Book Value"), "fieldname": "book_value", "fieldtype": "Currency", "width": 120},
        {"label": _("Method"), "fieldname": "depreciation_method", "fieldtype": "Data", "width": 130},
        {"label": _("Next 12mo Depreciation"), "fieldname": "annual_depreciation", "fieldtype": "Currency", "width": 160},
    ]
    for i in range(1, forecast_years + 1):
        yr = date.today().year + i
        columns.append({"label": f"FY {yr} Depreciation", "fieldname": f"fy_{yr}", "fieldtype": "Currency", "width": 150})

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
        SELECT a.name, a.asset_name, a.asset_category, a.default_finance_book
        FROM `tabAsset` a
        WHERE {conditions}
        ORDER BY a.asset_category, a.name
        """,
        values,
        as_dict=True,
    )
    if not assets:
        return columns, []

    asset_names = [a.name for a in assets]

    # Active depreciation schedules (the real, already-computed source of
    # truth) for these assets, one row per (asset, finance book).
    schedule_filters = {"asset": ["in", asset_names], "docstatus": 1, "status": "Active"}
    if filters.get("finance_book"):
        schedule_filters["finance_book"] = filters["finance_book"]

    schedules = frappe.get_all(
        "Asset Depreciation Schedule",
        filters=schedule_filters,
        fields=["name", "asset", "finance_book", "depreciation_method", "gross_purchase_amount"],
    )

    schedules_by_asset = defaultdict(list)
    for s in schedules:
        schedules_by_asset[s.asset].append(s)

    # When no finance_book filter is given, pick one schedule per asset:
    # prefer the asset's default_finance_book, else the first available.
    selected = {}
    if filters.get("finance_book"):
        for asset_name, rows in schedules_by_asset.items():
            selected[asset_name] = rows[0]
    else:
        default_book_by_asset = {a.name: a.default_finance_book for a in assets}
        for asset_name, rows in schedules_by_asset.items():
            preferred = default_book_by_asset.get(asset_name)
            match = next((r for r in rows if r.finance_book == preferred), None)
            selected[asset_name] = match or rows[0]

    selected_ads_names = [s.name for s in selected.values()]

    # Current book value per (asset, finance book), maintained by ERPNext core.
    finance_book_rows = frappe.get_all(
        "Asset Finance Book",
        filters={"parent": ["in", asset_names]},
        fields=["parent", "finance_book", "value_after_depreciation"],
    )
    book_value_map = {(r.parent, r.finance_book): r.value_after_depreciation for r in finance_book_rows}

    # Future scheduled depreciation entries for the selected schedules.
    future_entries = []
    if selected_ads_names:
        future_entries = frappe.get_all(
            "Depreciation Schedule",
            filters={"parent": ["in", selected_ads_names], "schedule_date": [">", getdate()]},
            fields=["parent", "schedule_date", "depreciation_amount"],
        )

    entries_by_ads = defaultdict(list)
    for e in future_entries:
        entries_by_ads[e.parent].append(e)

    today = getdate()
    data = []
    for a in assets:
        ads = selected.get(a.name)
        row = {
            "name": a.name,
            "asset_name": a.asset_name,
            "asset_category": a.asset_category,
        }

        if not ads:
            # No active depreciation schedule found for this asset/book —
            # nothing to forecast, but still list it so the gap is visible.
            row["finance_book"] = filters.get("finance_book") or a.default_finance_book
            row["book_value"] = 0
            row["depreciation_method"] = ""
            row["annual_depreciation"] = 0
            for i in range(1, forecast_years + 1):
                row[f"fy_{date.today().year + i}"] = 0
            data.append(row)
            continue

        row["finance_book"] = ads.finance_book
        row["depreciation_method"] = ads.depreciation_method
        row["book_value"] = flt(book_value_map.get((a.name, ads.finance_book)))

        rows = sorted(entries_by_ads.get(ads.name, []), key=lambda r: r.schedule_date)

        next_12mo_cutoff = today.replace(year=today.year + 1)
        row["annual_depreciation"] = sum(
            flt(r.depreciation_amount) for r in rows if r.schedule_date <= next_12mo_cutoff
        )

        for i in range(1, forecast_years + 1):
            yr = date.today().year + i
            row[f"fy_{yr}"] = sum(
                flt(r.depreciation_amount) for r in rows if r.schedule_date.year == yr
            )

        data.append(row)

    return columns, data
