import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Purchase Date"), "fieldname": "purchase_date", "fieldtype": "Date", "width": 120},
        {"label": _("Purchase Cost"), "fieldname": "gross_purchase_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Repair Cost"), "fieldname": "total_repair_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Total Cost of Ownership"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 180},
        {"label": _("Current Book Value"), "fieldname": "book_value", "fieldtype": "Currency", "width": 160},
        {"label": _("Total Cost / Book Value %"), "fieldname": "cost_ratio_pct", "fieldtype": "Percent", "width": 180},
        {"label": _("Age (Years)"), "fieldname": "age_years", "fieldtype": "Float", "precision": 1, "width": 100},
    ]

    conditions = "a.docstatus < 2"
    values = {}

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    if filters.get("from_date"):
        conditions += " AND a.purchase_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions += " AND a.purchase_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]

    data = frappe.db.sql(
        f"""
        SELECT
            a.name,
            a.asset_name,
            a.asset_category,
            a.purchase_date,
            a.gross_purchase_amount,
            IFNULL(a.custom_total_maintenance_cost, 0)                           AS total_repair_cost,
            a.gross_purchase_amount + IFNULL(a.custom_total_maintenance_cost, 0) AS total_cost,
            IFNULL(a.value_after_depreciation, a.gross_purchase_amount)          AS book_value,
            CASE
                WHEN IFNULL(a.value_after_depreciation, a.gross_purchase_amount) = 0 THEN 0
                ELSE ROUND(
                    (a.gross_purchase_amount + IFNULL(a.custom_total_maintenance_cost, 0)) * 100
                    / IFNULL(a.value_after_depreciation, a.gross_purchase_amount)
                , 1)
            END AS cost_ratio_pct,
            ROUND(DATEDIFF(CURDATE(), a.purchase_date) / 365.25, 1)             AS age_years
        FROM `tabAsset` a
        WHERE {conditions}
        ORDER BY total_cost DESC
        """,
        values,
        as_dict=True,
    )

    return columns, data
