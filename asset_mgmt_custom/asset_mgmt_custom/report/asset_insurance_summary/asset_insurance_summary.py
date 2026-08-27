import frappe
from frappe import _
from frappe.utils import date_diff, today, getdate


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Branch"), "fieldname": "custom_branch", "fieldtype": "Link", "options": "Branch", "width": 130},
        {"label": _("Insurer"), "fieldname": "insurer", "fieldtype": "Data", "width": 150},
        {"label": _("Policy Number"), "fieldname": "policy_number", "fieldtype": "Data", "width": 150},
        {"label": _("Start Date"), "fieldname": "insurance_start_date", "fieldtype": "Date", "width": 110},
        {"label": _("End Date"), "fieldname": "insurance_end_date", "fieldtype": "Date", "width": 110},
        {"label": _("Days Remaining"), "fieldname": "days_remaining", "fieldtype": "Int", "width": 100},
        {"label": _("Status"), "fieldname": "insurance_status", "fieldtype": "Data", "width": 120},
    ]


def get_data(filters):
    conds = "WHERE a.docstatus < 2"
    params = {}
    if filters.get("company"):
        conds += " AND a.company = %(company)s"
        params["company"] = filters["company"]
    if filters.get("branch"):
        conds += " AND a.custom_branch = %(branch)s"
        params["branch"] = filters["branch"]

    assets = frappe.db.sql(f"""
        SELECT name, asset_name, asset_category, custom_branch,
               insurer, policy_number, insurance_start_date, insurance_end_date
        FROM `tabAsset` a
        {conds}
        ORDER BY insurance_end_date ASC
    """, params, as_dict=True)

    rows = []
    today_date = today()
    for a in assets:
        if a.insurance_end_date:
            days_left = date_diff(a.insurance_end_date, today_date)
            if days_left < 0:
                status = "Expired"
            elif days_left <= 30:
                status = "Expiring Soon"
            else:
                status = "Active"
        else:
            days_left = None
            status = "No Insurance"

        status_filter = filters.get("status")
        if status_filter and status_filter != status:
            continue

        rows.append({
            "name": a.name,
            "asset_name": a.asset_name,
            "asset_category": a.asset_category,
            "custom_branch": a.custom_branch,
            "insurer": a.insurer or "",
            "policy_number": a.policy_number or "",
            "insurance_start_date": a.insurance_start_date,
            "insurance_end_date": a.insurance_end_date,
            "days_remaining": days_left,
            "insurance_status": status,
        })
    return rows
