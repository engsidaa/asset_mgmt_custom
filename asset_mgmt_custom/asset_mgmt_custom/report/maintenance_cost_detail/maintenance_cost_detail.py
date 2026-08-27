import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 120},
        {"label": _("Repair No"), "fieldname": "name", "fieldtype": "Link", "options": "Asset Repair", "width": 140},
        {"label": _("Failure Date"), "fieldname": "failure_date", "fieldtype": "Datetime", "width": 120},
        {"label": _("Status"), "fieldname": "repair_status", "fieldtype": "Data", "width": 100},
        {"label": _("Technician"), "fieldname": "custom_technician_name", "fieldtype": "Data", "width": 120},
        {"label": _("Repair Cost"), "fieldname": "repair_cost", "fieldtype": "Currency", "width": 120},
        {"label": _("Labor Cost"), "fieldname": "custom_labor_cost", "fieldtype": "Currency", "width": 110},
        {"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 120},
        {"label": _("CapEx"), "fieldname": "capitalize_repair_cost", "fieldtype": "Check", "width": 70},
        {"label": _("Warranty"), "fieldname": "custom_is_warranty_repair", "fieldtype": "Check", "width": 80},
    ]

    conditions = "WHERE ar.docstatus = 1"
    if filters.get("asset"):
        conditions += " AND ar.asset = %(asset)s"
    if filters.get("from_date"):
        conditions += " AND DATE(ar.failure_date) >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND DATE(ar.failure_date) <= %(to_date)s"
    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"

    data = frappe.db.sql(f"""
        SELECT
            ar.asset,
            a.asset_name,
            a.asset_category,
            ar.name,
            ar.failure_date,
            ar.repair_status,
            ar.custom_technician_name,
            ar.repair_cost,
            IFNULL(ar.custom_labor_cost, 0) AS custom_labor_cost,
            (ar.repair_cost + IFNULL(ar.custom_labor_cost, 0)) AS total_cost,
            ar.capitalize_repair_cost,
            ar.custom_is_warranty_repair
        FROM `tabAsset Repair` ar
        JOIN `tabAsset` a ON a.name = ar.asset
        {conditions}
        ORDER BY ar.failure_date DESC
    """, filters, as_dict=True)

    return columns, data
