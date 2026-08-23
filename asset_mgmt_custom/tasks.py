"""Scheduled tasks for asset_mgmt_custom."""
import frappe
from frappe import _
from frappe.utils import date_diff, today


def send_incomplete_asset_alerts():
    """
    Daily job: find assets that have been in 'Incomplete' status for > 3 days
    and send an in-app notification to users with the 'Assets Manager' role.
    """
    incomplete = frappe.db.sql("""
        SELECT name, asset_name, creation, company
        FROM `tabAsset`
        WHERE custom_operational_status = 'Incomplete'
          AND docstatus = 1
        ORDER BY creation ASC
    """, as_dict=True)

    if not incomplete:
        return

    managers = frappe.get_all(
        "Has Role",
        filters={"role": "Assets Manager", "parenttype": "User"},
        fields=["parent"],
    )
    manager_users = [m.parent for m in managers]

    for asset in incomplete:
        days_old = date_diff(today(), str(asset.creation)[:10])
        if days_old < 3:
            continue
        for user in manager_users:
            try:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": _("Incomplete Asset: {0} ({1} days)").format(
                        asset.asset_name or asset.name, days_old),
                    "email_content": _("Asset <b>{0}</b> has been incomplete for <b>{1} days</b>. "
                                       "Please tag and activate it.").format(
                        asset.asset_name or asset.name, days_old),
                    "document_type": "Asset",
                    "document_name": asset.name,
                    "for_user": user,
                    "type": "Alert",
                }).insert(ignore_permissions=True)
            except Exception:
                pass
