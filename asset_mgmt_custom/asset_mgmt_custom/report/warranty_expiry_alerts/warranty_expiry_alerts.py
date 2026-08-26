import frappe
from frappe import _
from frappe.utils import today, add_days


def execute(filters=None):
    filters = filters or {}
    days = int(filters.get("days") or 30)

    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Link", "options": "Location", "width": 130},
        {"label": _("Custodian"), "fieldname": "custodian", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Warranty Expiry"), "fieldname": "custom_warranty_expiry", "fieldtype": "Date", "width": 120},
        {"label": _("Days Remaining"), "fieldname": "days_remaining", "fieldtype": "Int", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]

    expiry_cutoff = add_days(today(), days)

    data = frappe.db.sql(
        """
        SELECT
            a.name          AS asset,
            a.asset_name,
            a.asset_category,
            a.location,
            a.custodian,
            a.custom_warranty_expiry,
            DATEDIFF(a.custom_warranty_expiry, CURDATE()) AS days_remaining,
            a.status
        FROM `tabAsset` a
        WHERE
            a.docstatus < 2
            AND a.custom_under_warranty = 1
            AND a.custom_warranty_expiry IS NOT NULL
            AND a.custom_warranty_expiry >= CURDATE()
            AND a.custom_warranty_expiry <= %(cutoff)s
            {category_cond}
            {location_cond}
        ORDER BY a.custom_warranty_expiry ASC
        """.format(
            category_cond="AND a.asset_category = %(asset_category)s" if filters.get("asset_category") else "",
            location_cond="AND a.location = %(location)s" if filters.get("location") else "",
        ),
        {
            "cutoff": expiry_cutoff,
            "asset_category": filters.get("asset_category"),
            "location": filters.get("location"),
        },
        as_dict=True,
    )

    for row in data:
        d = row.days_remaining or 0
        if d <= 14:
            row["color"] = "red"
        elif d <= 30:
            row["color"] = "orange"

    return columns, data
