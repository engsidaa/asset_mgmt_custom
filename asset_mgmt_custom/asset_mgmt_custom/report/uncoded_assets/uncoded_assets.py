import frappe
from frappe import _
from frappe.utils import date_diff, today


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Asset"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 190},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"label": _("Branch"), "fieldname": "custom_branch", "fieldtype": "Link", "options": "Branch", "width": 130},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Date", "width": 110},
        {"label": _("Days Uncoded"), "fieldname": "days", "fieldtype": "Int", "width": 110},
        {"label": _("Tag Type"), "fieldname": "custom_tag_type", "fieldtype": "Data", "width": 100},
        {"label": _("Before Photo?"), "fieldname": "has_before_photo", "fieldtype": "Check", "width": 100},
        {"label": _("After Photo?"), "fieldname": "has_after_photo", "fieldtype": "Check", "width": 100},
    ]


def get_data(filters):
    conditions = "custom_coding_status != 'Coded' AND docstatus = 1"
    values = {}

    if filters.get("asset_category"):
        conditions += " AND asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND company = %(company)s"
        values["company"] = filters["company"]

    if filters.get("custom_branch"):
        conditions += " AND custom_branch = %(custom_branch)s"
        values["custom_branch"] = filters["custom_branch"]

    assets = frappe.db.sql(
        f"""
        SELECT name, asset_name, asset_category, custom_branch, creation,
               custom_tag_type, custom_tagging_photo_before, custom_tagging_photo
        FROM `tabAsset`
        WHERE {conditions}
        ORDER BY creation ASC
        """,
        values,
        as_dict=True,
    )

    data = []
    for a in assets:
        a["days"] = date_diff(today(), str(a.creation)[:10])
        a["has_before_photo"] = 1 if a.custom_tagging_photo_before else 0
        a["has_after_photo"] = 1 if a.custom_tagging_photo else 0
        data.append(a)

    return data
