import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Repair"), "fieldname": "repair_name", "fieldtype": "Link", "options": "Asset Repair", "width": 160},
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"label": _("Completion Date"), "fieldname": "completion_date", "fieldtype": "Date", "width": 120},
        {"label": _("Repair Cost"), "fieldname": "repair_cost", "fieldtype": "Currency", "width": 120},
        {"label": _("Labor Cost"), "fieldname": "labor_cost", "fieldtype": "Currency", "width": 110},
        {"label": _("Total Cost"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
        {"label": _("CapEx Threshold"), "fieldname": "threshold", "fieldtype": "Currency", "width": 130},
        {"label": _("Excess over Threshold"), "fieldname": "excess", "fieldtype": "Currency", "width": 150},
        {"label": _("Warranty Repair"), "fieldname": "is_warranty_repair", "fieldtype": "Check", "width": 110},
    ]

    conditions = []
    values = {"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}

    if filters.get("asset"):
        conditions.append("ar.asset = %(asset)s")
        values["asset"] = filters["asset"]

    if filters.get("asset_category"):
        conditions.append("a.asset_category = %(asset_category)s")
        values["asset_category"] = filters["asset_category"]

    if filters.get("from_date"):
        conditions.append("ar.completion_date >= %(from_date)s")

    if filters.get("to_date"):
        conditions.append("ar.completion_date <= %(to_date)s")

    where_clause = ("AND " + " AND ".join(conditions)) if conditions else ""

    data = frappe.db.sql(
        """
        SELECT
            ar.name                                                     AS repair_name,
            ar.asset,
            a.asset_name,
            a.asset_category,
            ar.completion_date,
            ar.repair_cost,
            IFNULL(ar.custom_labor_cost, 0)                             AS labor_cost,
            ar.repair_cost + IFNULL(ar.custom_labor_cost, 0)            AS grand_total,
            IFNULL(ac.custom_capitalization_threshold, 0)               AS threshold,
            (ar.repair_cost + IFNULL(ar.custom_labor_cost, 0))
              - IFNULL(ac.custom_capitalization_threshold, 0)            AS excess,
            ar.custom_is_warranty_repair                                AS is_warranty_repair
        FROM `tabAsset Repair` ar
        LEFT JOIN `tabAsset` a  ON a.name  = ar.asset
        LEFT JOIN `tabAsset Category` ac ON ac.name = a.asset_category
        WHERE
            ar.docstatus = 1
            AND ar.capitalize_repair_cost = 1
            {where}
        ORDER BY ar.completion_date DESC
        """.format(where=where_clause),
        values,
        as_dict=True,
    )

    # summary row totals (handled by add_total_row in report JSON)
    return columns, data
