import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
        {"label": _("Last Inspection"), "fieldname": "last_inspection_date", "fieldtype": "Date", "width": 130},
        {"label": _("Inspector"), "fieldname": "inspector", "fieldtype": "Data", "width": 140},
        {"label": _("Overall Result"), "fieldname": "overall_result", "fieldtype": "Data", "width": 110},
        {"label": _("Next Inspection"), "fieldname": "next_inspection_date", "fieldtype": "Date", "width": 130},
        {"label": _("# Inspections"), "fieldname": "inspection_count", "fieldtype": "Int", "width": 100},
    ]

    outer_conds = ""
    params = {}
    if filters.get("branch"):
        outer_conds += " AND s1.branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("overall_result"):
        outer_conds += " AND s1.overall_result = %(overall_result)s"
        params["overall_result"] = filters["overall_result"]
    if filters.get("from_date"):
        outer_conds += " AND s1.inspection_date >= %(from_date)s"
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        outer_conds += " AND s1.inspection_date <= %(to_date)s"
        params["to_date"] = filters["to_date"]

    data = frappe.db.sql(f"""
        SELECT
            s1.asset,
            s1.asset_name,
            s1.branch,
            s1.inspection_date AS last_inspection_date,
            s1.inspector,
            s1.overall_result,
            s1.next_inspection_date,
            cnt.inspection_count
        FROM `tabAsset Safety Inspection` s1
        JOIN (
            SELECT asset, MAX(inspection_date) AS max_date
            FROM `tabAsset Safety Inspection`
            WHERE docstatus = 1
            GROUP BY asset
        ) latest ON s1.asset = latest.asset AND s1.inspection_date = latest.max_date
        JOIN (
            SELECT asset, COUNT(*) AS inspection_count
            FROM `tabAsset Safety Inspection`
            WHERE docstatus = 1
            GROUP BY asset
        ) cnt ON cnt.asset = s1.asset
        WHERE s1.docstatus = 1
        {outer_conds}
        ORDER BY s1.branch, s1.asset
    """, params, as_dict=True)

    return columns, data
