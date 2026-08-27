import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 150},
        {"label": _("Total Scheduled"), "fieldname": "total_scheduled", "fieldtype": "Int", "width": 130},
        {"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 110},
        {"label": _("Missed"), "fieldname": "missed", "fieldtype": "Int", "width": 100},
        {"label": _("Skipped"), "fieldname": "skipped", "fieldtype": "Int", "width": 100},
        {"label": _("Compliance %"), "fieldname": "compliance_pct", "fieldtype": "Percent", "width": 120},
    ]

    conds = "WHERE 1=1"
    params = {}
    if filters.get("branch"):
        conds += " AND branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("from_date"):
        conds += " AND scheduled_date >= %(from_date)s"
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conds += " AND scheduled_date <= %(to_date)s"
        params["to_date"] = filters["to_date"]

    raw = frappe.db.sql(f"""
        SELECT branch,
               COUNT(*) AS total_scheduled,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) AS missed,
               SUM(CASE WHEN status = 'Skipped' THEN 1 ELSE 0 END) AS skipped
        FROM `tabAsset Cleaning Schedule`
        {conds}
        GROUP BY branch
        ORDER BY branch
    """, params, as_dict=True)

    for r in raw:
        total = r.total_scheduled or 0
        comp = r.completed or 0
        r["compliance_pct"] = round((comp / total * 100), 1) if total else 0

    return columns, raw
