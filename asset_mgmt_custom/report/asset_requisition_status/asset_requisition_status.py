import frappe
from frappe import _
from frappe.utils import date_diff, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Requisition"), "fieldname": "name", "fieldtype": "Link", "options": "Asset Requisition", "width": 150},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 130},
        {"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
        {"label": _("Qty"), "fieldname": "quantity", "fieldtype": "Int", "width": 60},
        {"label": _("Request Date"), "fieldname": "request_date", "fieldtype": "Date", "width": 110},
        {"label": _("Required By"), "fieldname": "required_by", "fieldtype": "Date", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Spare Available"), "fieldname": "spare_available", "fieldtype": "Check", "width": 110},
        {"label": _("Spare Asset"), "fieldname": "spare_asset", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Days Waiting"), "fieldname": "days_waiting", "fieldtype": "Int", "width": 110},
    ]

    conditions = "WHERE 1=1"
    if filters.get("status"):
        conditions += " AND status = %(status)s"
    if filters.get("department"):
        conditions += " AND department = %(department)s"
    if filters.get("from_date"):
        conditions += " AND request_date >= %(from_date)s"

    data = frappe.db.sql(f"""
        SELECT name, employee, department, asset_category, item_code,
               quantity, request_date, required_by, status,
               spare_available, spare_asset
        FROM `tabAsset Requisition`
        {conditions}
        ORDER BY request_date DESC
    """, filters, as_dict=True)

    for row in data:
        if row.status not in ("Fulfilled", "Rejected"):
            row["days_waiting"] = date_diff(today(), str(row.request_date))
        else:
            row["days_waiting"] = 0

    return columns, data
