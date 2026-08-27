import frappe
from frappe import _
from frappe.utils import today


def execute(filters=None):
    filters = filters or {}
    if not filters.get("cost_center"):
        frappe.throw(_("Branch / Cost Center is required"))

    as_of = filters.get("as_of_date") or today()

    columns = [
        {"label": _("#"), "fieldname": "idx", "fieldtype": "Int", "width": 45},
        {"label": _("Asset Code"), "fieldname": "asset", "fieldtype": "Link",
         "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 190},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link",
         "options": "Asset Category", "width": 130},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 120},
        {"label": _("Purchase Date"), "fieldname": "purchase_date",
         "fieldtype": "Date", "width": 105},
        {"label": _("Gross Block"), "fieldname": "gross_purchase_amount",
         "fieldtype": "Currency", "width": 120},
        {"label": _("Net Book Value"), "fieldname": "net_book_value",
         "fieldtype": "Currency", "width": 120},
        {"label": _("Condition"), "fieldname": "custom_asset_condition",
         "fieldtype": "Data", "width": 90},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
        {"label": _("Custodian"), "fieldname": "custodian", "fieldtype": "Data", "width": 120},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 150},
    ]

    data = frappe.db.sql("""
        SELECT
            a.name                          AS asset,
            a.asset_name,
            a.asset_category,
            a.location,
            a.purchase_date,
            a.gross_purchase_amount,
            a.value_after_depreciation      AS net_book_value,
            a.custom_asset_condition,
            a.status,
            a.custodian,
            '' AS remarks
        FROM `tabAsset` a
        WHERE a.docstatus = 1
          AND a.cost_center = %(cost_center)s
          AND a.status NOT IN ('Scrapped', 'Sold')
          AND (a.purchase_date IS NULL OR a.purchase_date <= %(as_of_date)s)
        ORDER BY a.asset_category, a.name
    """, {"cost_center": filters["cost_center"], "as_of_date": as_of}, as_dict=True)

    for i, row in enumerate(data, 1):
        row["idx"] = i

    # Signature footer rows
    outgoing = filters.get("outgoing_manager") or "________________________"
    incoming = filters.get("incoming_manager") or "________________________"
    data += [
        {},
        {"asset_name": _("Outgoing Manager: {0}").format(outgoing), "remarks": _("Signature: ________________________")},
        {"asset_name": _("Incoming Manager: {0}").format(incoming), "remarks": _("Signature: ________________________")},
        {"asset_name": _("Date: {0}").format(as_of)},
    ]

    return columns, data
