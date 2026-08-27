import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    threshold_pct = flt(filters.get("threshold_percent") or 30)

    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link", "options": "Location", "width": 140},
        {"label": _("Gross Value"), "fieldname": "gross_purchase_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Current Value"), "fieldname": "current_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Total Repair Cost"), "fieldname": "total_repair_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Repair / Value %"), "fieldname": "repair_ratio_pct", "fieldtype": "Percent", "width": 130},
        {"label": _("Flag"), "fieldname": "flag", "fieldtype": "Data", "width": 140},
    ]

    conditions = "a.docstatus < 2"
    values = {"threshold_pct": threshold_pct}

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
            a.gross_purchase_amount,
            IFNULL(a.value_after_depreciation, a.gross_purchase_amount) AS current_value,
            IFNULL(a.custom_total_maintenance_cost, 0)                  AS total_repair_cost,
            CASE
                WHEN IFNULL(a.value_after_depreciation, a.gross_purchase_amount) = 0 THEN 0
                ELSE ROUND(
                    IFNULL(a.custom_total_maintenance_cost, 0) * 100
                    / IFNULL(a.value_after_depreciation, a.gross_purchase_amount)
                , 1)
            END AS repair_ratio_pct
        FROM `tabAsset` a
        WHERE {conditions}
        HAVING repair_ratio_pct > 0
        ORDER BY repair_ratio_pct DESC
        """,
        values,
        as_dict=True,
    )

    for row in data:
        pct = flt(row.repair_ratio_pct, 1)
        if pct >= threshold_pct:
            row["flag"] = "⚠ Consider Replace"
        elif pct >= threshold_pct * 0.7:
            row["flag"] = "⚡ Monitor"
        else:
            row["flag"] = ""

    return columns, data
