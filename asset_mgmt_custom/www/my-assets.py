import frappe
from frappe import _


def get_context(context):
    context.no_cache = 1
    context.title = _("My Assets")

    if frappe.session.user == "Guest":
        context.assets = []
        return

    # Find employee linked to current user
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        context.assets = []
        return

    # Assets currently in this employee's custody
    assets = frappe.db.sql("""
        SELECT
            a.name, a.asset_name, a.asset_category, a.location, a.status,
            a.custom_operational_status, a.custom_sticker_code, a.custom_iron_code,
            am.transaction_date AS assigned_date
        FROM `tabAsset Movement Item` ami
        JOIN `tabAsset Movement` am ON am.name = ami.parent
        JOIN `tabAsset` a ON a.name = ami.asset
        WHERE am.docstatus = 1
          AND ami.to_employee = %(employee)s
          AND ami.asset NOT IN (
              SELECT ri.asset FROM `tabAsset Movement Item` ri
              JOIN `tabAsset Movement` rm ON rm.name = ri.parent
              WHERE rm.docstatus = 1 AND ri.from_employee = %(employee)s
          )
        ORDER BY am.transaction_date DESC
    """, {"employee": employee}, as_dict=True)

    context.assets = assets
