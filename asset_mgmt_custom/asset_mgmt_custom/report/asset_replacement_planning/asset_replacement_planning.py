import frappe
from frappe import _
from frappe.utils import today, date_diff


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
        {"label": _("Purchase Date"), "fieldname": "purchase_date", "fieldtype": "Date", "width": 110},
        {"label": _("Age (Years)"), "fieldname": "age_years", "fieldtype": "Float", "width": 100},
        {"label": _("Gross Value"), "fieldname": "gross_purchase_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Current Value"), "fieldname": "current_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Total Maintenance Cost"), "fieldname": "total_maintenance", "fieldtype": "Currency", "width": 160},
        {"label": _("Maintenance/Value (%)"), "fieldname": "maintenance_ratio", "fieldtype": "Percent", "width": 160},
        {"label": _("Downtime Hours"), "fieldname": "downtime_hours", "fieldtype": "Float", "width": 130},
        {"label": _("Repair Count"), "fieldname": "repair_count", "fieldtype": "Int", "width": 110},
        {"label": _("Recommendation"), "fieldname": "recommendation", "fieldtype": "Data", "width": 160},
    ]


def get_data(filters):
    age_threshold = filters.get("age_threshold_years") or 5
    ratio_threshold = filters.get("maintenance_cost_ratio_threshold") or 30

    conditions = "WHERE a.docstatus < 2 AND a.status NOT IN ('Scrapped', 'Sold')"
    params = {}

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        params["company"] = filters["company"]
    if filters.get("branch"):
        conditions += " AND a.custom_branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    assets = frappe.db.sql(f"""
        SELECT
            a.name, a.asset_name, a.asset_category,
            a.custom_branch AS branch,
            a.purchase_date,
            a.gross_purchase_amount,
            COALESCE(a.value_after_depreciation, a.gross_purchase_amount) AS current_value,
            COALESCE(a.custom_total_maintenance_cost, 0) AS total_maintenance,
            COALESCE(a.custom_total_downtime_hours, 0) AS downtime_hours
        FROM `tabAsset` a
        {conditions}
        ORDER BY a.purchase_date ASC
    """, params, as_dict=True)

    if not assets:
        return []

    asset_names = [a.name for a in assets]

    repair_counts = frappe.db.sql("""
        SELECT asset, COUNT(*) AS cnt
        FROM `tabAsset Repair`
        WHERE asset IN %(names)s AND docstatus = 1
        GROUP BY asset
    """, {"names": asset_names}, as_dict=True)
    repair_map = {r.asset: r.cnt for r in repair_counts}

    rows = []
    for a in assets:
        if not a.purchase_date:
            continue
        age_days = date_diff(today(), str(a.purchase_date))
        age_years = round(age_days / 365.25, 1)

        current_value = a.current_value or a.gross_purchase_amount or 0
        total_maint = a.total_maintenance or 0
        ratio = round((total_maint / current_value * 100), 1) if current_value > 0 else 0
        repair_count = repair_map.get(a.name, 0)

        flags = []
        if age_years >= age_threshold:
            flags.append("Old")
        if ratio >= ratio_threshold:
            flags.append("High Maint Cost")
        if a.downtime_hours and a.downtime_hours > 100:
            flags.append("High Downtime")

        if len(flags) >= 2:
            recommendation = _("Replace Soon")
        elif len(flags) == 1:
            recommendation = _("Monitor — {0}").format(flags[0])
        else:
            recommendation = _("Keep")

        rows.append({
            "name": a.name,
            "asset_name": a.asset_name,
            "asset_category": a.asset_category,
            "branch": a.branch,
            "purchase_date": a.purchase_date,
            "age_years": age_years,
            "gross_purchase_amount": a.gross_purchase_amount or 0,
            "current_value": current_value,
            "total_maintenance": total_maint,
            "maintenance_ratio": ratio,
            "downtime_hours": a.downtime_hours or 0,
            "repair_count": repair_count,
            "recommendation": recommendation,
        })

    rows.sort(key=lambda r: (-r["maintenance_ratio"], -r["age_years"]))
    return rows
