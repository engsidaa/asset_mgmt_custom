import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Part ID"), "fieldname": "name", "fieldtype": "Link", "options": "Asset Spare Part", "width": 140},
        {"label": _("Part Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 150},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link", "options": "Location", "width": 130},
        {"label": _("Quantity"), "fieldname": "quantity", "fieldtype": "Float", "width": 100},
        {"label": _("Min Qty"), "fieldname": "minimum_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Status"), "fieldname": "stock_status", "fieldtype": "Data", "width": 100},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
        {"label": _("Unit Cost"), "fieldname": "unit_cost", "fieldtype": "Currency", "width": 110},
    ]

    conds = "WHERE 1=1"
    params = {}
    if filters.get("asset_category"):
        conds += " AND asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    parts = frappe.db.sql(f"""
        SELECT name, item_name, asset_category, location,
               quantity, minimum_qty, supplier, unit_cost
        FROM `tabAsset Spare Part`
        {conds}
        ORDER BY item_name
    """, params, as_dict=True)

    status_filter = filters.get("stock_status") or "All"
    rows = []
    for p in parts:
        qty = p.quantity or 0
        min_q = p.minimum_qty or 0
        if qty == 0:
            status = "Critical"
        elif min_q > 0 and qty < min_q:
            status = "Low"
        else:
            status = "OK"

        if status_filter != "All" and status != status_filter:
            continue

        p["stock_status"] = status
        rows.append(p)

    return columns, rows
