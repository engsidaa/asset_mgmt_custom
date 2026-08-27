import frappe
from frappe import _
from frappe.utils import date_diff, today, now_datetime


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Checkout"), "fieldname": "name", "fieldtype": "Link", "options": "Asset Checkout", "width": 140},
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Checked Out By"), "fieldname": "checked_out_by", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
        {"label": _("Checkout Date"), "fieldname": "checkout_datetime", "fieldtype": "Datetime", "width": 150},
        {"label": _("Expected Return"), "fieldname": "expected_return", "fieldtype": "Datetime", "width": 150},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 100},
    ]

    conds = "WHERE docstatus = 1"
    params = {}
    if filters.get("branch"):
        conds += " AND branch = %(branch)s"
        params["branch"] = filters["branch"]
    if filters.get("status"):
        conds += " AND status = %(status)s"
        params["status"] = filters["status"]

    rows = frappe.db.sql(f"""
        SELECT name, asset, asset_name, checked_out_by, branch,
               checkout_datetime, expected_return, status, actual_return_datetime
        FROM `tabAsset Checkout`
        {conds}
        ORDER BY expected_return ASC
    """, params, as_dict=True)

    for r in rows:
        if r.status in ("Checked Out", "Overdue") and r.expected_return:
            overdue = date_diff(today(), str(r.expected_return)[:10])
            r["days_overdue"] = max(0, overdue)
        else:
            r["days_overdue"] = 0
    return columns, rows
