import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Incident"), "fieldname": "name", "fieldtype": "Link", "options": "Asset Incident Report", "width": 150},
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
        {"label": _("Incident Date"), "fieldname": "incident_date", "fieldtype": "Datetime", "width": 150},
        {"label": _("Type"), "fieldname": "incident_type", "fieldtype": "Data", "width": 130},
        {"label": _("Severity"), "fieldname": "severity", "fieldtype": "Data", "width": 90},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Injury"), "fieldname": "injury_involved", "fieldtype": "Check", "width": 80},
        {"label": _("Est. Damage"), "fieldname": "estimated_damage_cost", "fieldtype": "Currency", "width": 140},
    ]

    conds = "WHERE docstatus = 1"
    params = {}
    if filters.get("branch"):
        conds += " AND branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("from_date"):
        conds += " AND DATE(incident_date) >= %(from_date)s"
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conds += " AND DATE(incident_date) <= %(to_date)s"
        params["to_date"] = filters["to_date"]
    if filters.get("severity"):
        conds += " AND severity = %(severity)s"
        params["severity"] = filters["severity"]
    if filters.get("status"):
        conds += " AND status = %(status)s"
        params["status"] = filters["status"]

    data = frappe.db.sql(f"""
        SELECT name, asset, branch, incident_date, incident_type,
               severity, status, injury_involved, estimated_damage_cost
        FROM `tabAsset Incident Report`
        {conds}
        ORDER BY incident_date DESC
    """, params, as_dict=True)

    return columns, data
