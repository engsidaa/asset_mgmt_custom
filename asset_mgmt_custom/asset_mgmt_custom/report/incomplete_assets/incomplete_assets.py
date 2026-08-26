import frappe
from frappe import _
from frappe.utils import date_diff, today


def execute(filters=None):
    columns = [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Date", "width": 110},
        {"label": _("Days Incomplete"), "fieldname": "days", "fieldtype": "Int", "width": 120},
        {"label": _("Tag Type"), "fieldname": "custom_tag_type", "fieldtype": "Data", "width": 100},
        {"label": _("Sticker Code"), "fieldname": "custom_sticker_code", "fieldtype": "Data", "width": 120},
        {"label": _("Iron Code"), "fieldname": "custom_iron_code", "fieldtype": "Data", "width": 120},
    ]

    assets = frappe.db.sql("""
        SELECT name, asset_name, asset_category, company, creation,
               custom_tag_type, custom_sticker_code, custom_iron_code
        FROM `tabAsset`
        WHERE custom_operational_status = 'Incomplete'
          AND docstatus = 1
        ORDER BY creation ASC
    """, as_dict=True)

    data = []
    for a in assets:
        a["days"] = date_diff(today(), str(a.creation)[:10])
        data.append(a)

    return columns, data
