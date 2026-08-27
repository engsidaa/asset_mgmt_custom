import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Department / Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 200},
        {"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 160},
        {"label": _("Asset Count"), "fieldname": "asset_count", "fieldtype": "Int", "width": 110},
        {"label": _("Gross Value"), "fieldname": "gross_value", "fieldtype": "Currency", "width": 150},
        {"label": _("Current Book Value"), "fieldname": "book_value", "fieldtype": "Currency", "width": 160},
        {"label": _("Total Depreciation"), "fieldname": "total_depreciation", "fieldtype": "Currency", "width": 160},
        {"label": _("Total Repair Cost"), "fieldname": "total_repair_cost", "fieldtype": "Currency", "width": 150},
    ]

    conditions = "a.docstatus < 2"
    values = {}

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    data = frappe.db.sql(
        f"""
        SELECT
            a.cost_center,
            a.asset_category,
            COUNT(a.name)                                                     AS asset_count,
            SUM(a.gross_purchase_amount)                                      AS gross_value,
            SUM(IFNULL(a.value_after_depreciation, a.gross_purchase_amount))  AS book_value,
            SUM(a.gross_purchase_amount
                - IFNULL(a.value_after_depreciation, a.gross_purchase_amount)) AS total_depreciation,
            SUM(IFNULL(a.custom_total_maintenance_cost, 0))                   AS total_repair_cost
        FROM `tabAsset` a
        WHERE {conditions}
        GROUP BY a.cost_center, a.asset_category
        ORDER BY a.cost_center, a.asset_category
        """,
        values,
        as_dict=True,
    )

    return columns, data
