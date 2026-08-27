import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link",
         "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link",
         "options": "Asset Category", "width": 130},
        {"label": _("Branch / Cost Center"), "fieldname": "cost_center", "fieldtype": "Link",
         "options": "Cost Center", "width": 150},
        {"label": _("Repair No"), "fieldname": "repair_name", "fieldtype": "Link",
         "options": "Asset Repair", "width": 130},
        {"label": _("Failure Date"), "fieldname": "failure_date",
         "fieldtype": "Datetime", "width": 140},
        {"label": _("Completion Date"), "fieldname": "completion_date",
         "fieldtype": "Datetime", "width": 140},
        {"label": _("Downtime (hrs)"), "fieldname": "downtime_hours",
         "fieldtype": "Float", "precision": 2, "width": 110},
        {"label": _("Repair Cost"), "fieldname": "repair_cost",
         "fieldtype": "Currency", "width": 120},
        {"label": _("Repair Status"), "fieldname": "repair_status",
         "fieldtype": "Data", "width": 100},
    ]

    conditions = "WHERE ar.docstatus = 1 AND a.company = %(company)s"

    if filters.get("from_date"):
        conditions += " AND DATE(ar.failure_date) >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND DATE(ar.failure_date) <= %(to_date)s"
    if filters.get("cost_center"):
        conditions += " AND a.cost_center = %(cost_center)s"
    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"

    data = frappe.db.sql(f"""
        SELECT
            ar.asset,
            a.asset_name,
            a.asset_category,
            a.cost_center,
            ar.name                                     AS repair_name,
            ar.failure_date,
            ar.completion_date,
            IFNULL(ar.custom_downtime_hours, 0)         AS downtime_hours,
            ar.repair_cost,
            ar.repair_status
        FROM `tabAsset Repair` ar
        JOIN `tabAsset` a ON a.name = ar.asset
        {conditions}
        ORDER BY a.cost_center, ar.asset, ar.failure_date DESC
    """, filters, as_dict=True)

    return columns, data
