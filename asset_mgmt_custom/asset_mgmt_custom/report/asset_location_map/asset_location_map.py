import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link", "options": "Location", "width": 180},
        {"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 160},
        {"label": _("Asset Count"), "fieldname": "asset_count", "fieldtype": "Int", "width": 110},
        {"label": _("Active"), "fieldname": "active_count", "fieldtype": "Int", "width": 90},
        {"label": _("Scrapped"), "fieldname": "scrapped_count", "fieldtype": "Int", "width": 95},
        {"label": _("In Maintenance"), "fieldname": "maintenance_count", "fieldtype": "Int", "width": 120},
        {"label": _("Gross Value"), "fieldname": "gross_value", "fieldtype": "Currency", "width": 150},
        {"label": _("Book Value"), "fieldname": "book_value", "fieldtype": "Currency", "width": 140},
    ]

    conditions = "a.docstatus < 2"
    values = {}

    if filters.get("location"):
        conditions += " AND a.location = %(location)s"
        values["location"] = filters["location"]

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    data = frappe.db.sql(
        f"""
        SELECT
            a.location,
            a.asset_category,
            COUNT(a.name)                                                       AS asset_count,
            SUM(CASE WHEN a.status = 'Submitted' THEN 1 ELSE 0 END)            AS active_count,
            SUM(CASE WHEN a.status = 'Scrapped' THEN 1 ELSE 0 END)             AS scrapped_count,
            SUM(CASE WHEN a.status = 'Out of Order' THEN 1 ELSE 0 END)         AS maintenance_count,
            SUM(a.gross_purchase_amount)                                        AS gross_value,
            SUM(IFNULL(a.value_after_depreciation, a.gross_purchase_amount))    AS book_value
        FROM `tabAsset` a
        WHERE {conditions}
        GROUP BY a.location, a.asset_category
        ORDER BY a.location, a.asset_category
        """,
        values,
        as_dict=True,
    )

    return columns, data
