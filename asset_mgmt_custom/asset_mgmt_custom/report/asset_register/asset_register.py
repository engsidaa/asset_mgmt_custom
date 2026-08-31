import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset Code"), "fieldname": "asset", "fieldtype": "Link",
         "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link",
         "options": "Asset Category", "width": 130},
        {"label": _("Branch"), "fieldname": "custom_branch", "fieldtype": "Link",
         "options": "Branch", "width": 110},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link",
         "options": "Location", "width": 120},
        {"label": _("Custodian"), "fieldname": "custodian", "fieldtype": "Link",
         "options": "Employee", "width": 120},
        {"label": _("Purchase Date"), "fieldname": "purchase_date",
         "fieldtype": "Date", "width": 105},
        {"label": _("Available-for-use Date"), "fieldname": "available_for_use_date",
         "fieldtype": "Date", "width": 130},
        {"label": _("Gross Block"), "fieldname": "gross_purchase_amount",
         "fieldtype": "Currency", "width": 130},
        {"label": _("Opening Accum. Dep."), "fieldname": "opening_accumulated_depreciation",
         "fieldtype": "Currency", "width": 140},
        {"label": _("Accumulated Depreciation"), "fieldname": "accumulated_depreciation",
         "fieldtype": "Currency", "width": 155},
        {"label": _("Net Book Value"), "fieldname": "net_book_value",
         "fieldtype": "Currency", "width": 130},
        {"label": _("Dep. Method"), "fieldname": "depreciation_method",
         "fieldtype": "Data", "width": 110},
        {"label": _("Useful Life (Months)"), "fieldname": "total_number_of_depreciations",
         "fieldtype": "Int", "width": 115},
        {"label": _("Booked Dep. Entries"), "fieldname": "booked_depreciations",
         "fieldtype": "Int", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link",
         "options": "Cost Center", "width": 130},
    ]

    conditions = "WHERE a.docstatus < 2"

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"

    if not filters.get("include_scrapped"):
        conditions += " AND a.status NOT IN ('Scrapped', 'Sold')"

    if filters.get("status"):
        conditions += " AND a.status = %(status)s"

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"

    if filters.get("branch"):
        conditions += " AND a.custom_branch = %(branch)s"

    if filters.get("location"):
        conditions += " AND a.location = %(location)s"

    data = frappe.db.sql(f"""
        SELECT
            a.name                              AS asset,
            a.asset_name,
            a.asset_category,
            a.custom_branch,
            a.location,
            a.custodian,
            a.purchase_date,
            a.available_for_use_date,
            a.gross_purchase_amount,
            IFNULL(a.opening_accumulated_depreciation, 0)
                                                AS opening_accumulated_depreciation,
            (a.gross_purchase_amount - a.value_after_depreciation)
                                                AS accumulated_depreciation,
            a.value_after_depreciation          AS net_book_value,
            afb.depreciation_method,
            afb.total_number_of_depreciations,
            IFNULL(afb.total_number_of_booked_depreciations, 0)
                                                AS booked_depreciations,
            a.status,
            a.cost_center
        FROM `tabAsset` a
        LEFT JOIN `tabAsset Finance Book` afb
            ON afb.parent = a.name AND afb.parenttype = 'Asset'
        {conditions}
        ORDER BY a.asset_category, a.name
    """, filters, as_dict=True)

    return columns, data
