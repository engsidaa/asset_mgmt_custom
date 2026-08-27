import frappe
from frappe import _
from frappe.utils import today, add_days


def execute(filters=None):
    filters = filters or {}
    days = int(filters.get("days") or 30)

    columns = [
        {"label": _("Task"), "fieldname": "task_name", "fieldtype": "Link", "options": "Asset Maintenance Task", "width": 160},
        {"label": _("Asset"), "fieldname": "asset_name", "fieldtype": "Link", "options": "Asset", "width": 140},
        {"label": _("Maintenance Type"), "fieldname": "maintenance_type", "fieldtype": "Data", "width": 140},
        {"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 110},
        {"label": _("Next Due Date"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 120},
        {"label": _("Days Until Due"), "fieldname": "days_until_due", "fieldtype": "Int", "width": 110},
        {"label": _("Assigned To"), "fieldname": "assign_to_name", "fieldtype": "Data", "width": 150},
        {"label": _("Last Completion Date"), "fieldname": "last_completion_date", "fieldtype": "Date", "width": 150},
        {"label": _("Maintenance Status"), "fieldname": "maintenance_status", "fieldtype": "Data", "width": 130},
    ]

    cutoff = add_days(today(), days)

    conditions = "mt.next_due_date IS NOT NULL AND mt.next_due_date <= %(cutoff)s AND mt.maintenance_status != 'Completed'"
    values = {"cutoff": cutoff, "today": today()}

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        values["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND am.company = %(company)s"
        values["company"] = filters["company"]

    data = frappe.db.sql(
        f"""
        SELECT
            mt.name                                                  AS task_name,
            am.asset_name,
            mt.maintenance_type,
            mt.start_date,
            mt.next_due_date,
            DATEDIFF(mt.next_due_date, CURDATE())                    AS days_until_due,
            mt.assign_to_name,
            mt.last_completion_date,
            mt.maintenance_status
        FROM `tabAsset Maintenance Task` mt
        JOIN `tabAsset Maintenance` am ON am.name = mt.parent
        LEFT JOIN `tabAsset` a ON a.name = am.asset_name
        WHERE {conditions}
        ORDER BY mt.next_due_date ASC
        """,
        values,
        as_dict=True,
    )

    for row in data:
        d = row.days_until_due or 0
        if d < 0:
            row["_style"] = "background-color: #fee2e2"
        elif d <= 7:
            row["_style"] = "background-color: #fef3c7"

    return columns, data
