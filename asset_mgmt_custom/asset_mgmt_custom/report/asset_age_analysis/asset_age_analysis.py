import frappe
from frappe import _
from frappe.utils import flt, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link", "options": "Location", "width": 140},
        {"label": _("Purchase Date"), "fieldname": "purchase_date", "fieldtype": "Date", "width": 120},
        {"label": _("Age (Years)"), "fieldname": "age_years", "fieldtype": "Float", "precision": 1, "width": 100},
        {"label": _("Age Bracket"), "fieldname": "age_bracket", "fieldtype": "Data", "width": 120},
        {"label": _("Gross Purchase Amount"), "fieldname": "gross_purchase_amount", "fieldtype": "Currency", "width": 160},
        {"label": _("Current Value"), "fieldname": "value_after_depreciation", "fieldtype": "Currency", "width": 140},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]

    conditions = "a.docstatus < 2 AND a.purchase_date IS NOT NULL"
    values = {}

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        values["company"] = filters["company"]

    data = frappe.db.sql(
        f"""
        SELECT
            a.name,
            a.asset_name,
            a.asset_category,
            a.location,
            a.purchase_date,
            ROUND(DATEDIFF(CURDATE(), a.purchase_date) / 365.25, 1) AS age_years,
            a.gross_purchase_amount,
            IFNULL(a.value_after_depreciation, a.gross_purchase_amount) AS value_after_depreciation,
            a.status
        FROM `tabAsset` a
        WHERE {conditions}
        ORDER BY a.purchase_date ASC
        """,
        values,
        as_dict=True,
    )

    for row in data:
        y = flt(row.age_years, 1)
        if y < 1:
            row["age_bracket"] = "< 1 Year"
        elif y < 3:
            row["age_bracket"] = "1 – 3 Years"
        elif y < 5:
            row["age_bracket"] = "3 – 5 Years"
        else:
            row["age_bracket"] = "5+ Years"

    return columns, data
