import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 150},
        {"label": _("Month"), "fieldname": "log_month", "fieldtype": "Data", "width": 110},
        {"label": _("Asset Count"), "fieldname": "asset_count", "fieldtype": "Int", "width": 100},
        {"label": _("Total kWh"), "fieldname": "total_units", "fieldtype": "Float", "width": 130},
        {"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Avg Cost/kWh"), "fieldname": "avg_cost_per_unit", "fieldtype": "Currency", "width": 150},
    ]

    conds = "WHERE 1=1"
    params = {}
    if filters.get("branch"):
        conds += " AND branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("from_month"):
        conds += " AND log_month >= %(from_month)s"
        params["from_month"] = filters["from_month"]
    if filters.get("to_month"):
        conds += " AND log_month <= %(to_month)s"
        params["to_month"] = filters["to_month"]

    data = frappe.db.sql(f"""
        SELECT branch,
               log_month,
               COUNT(DISTINCT asset) AS asset_count,
               SUM(units_consumed) AS total_units,
               SUM(total_cost) AS total_cost,
               CASE WHEN SUM(units_consumed) > 0
                    THEN SUM(total_cost) / SUM(units_consumed)
                    ELSE 0 END AS avg_cost_per_unit
        FROM `tabAsset Energy Log`
        {conds}
        GROUP BY branch, log_month
        ORDER BY branch, log_month
    """, params, as_dict=True)

    return columns, data
