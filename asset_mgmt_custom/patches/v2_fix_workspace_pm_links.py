"""
Clean up stale 'Asset Preventive Maintenance Schedule' links from all Workspace
records. The v1 patch targeted the wrong workspace name; this patch sweeps all
workspaces unconditionally so no stale links remain.
"""
import frappe


def execute():
    dt_name = "Asset Preventive Maintenance Schedule"

    # Delete from all workspaces, not just a specific one
    frappe.db.sql(
        "DELETE FROM `tabWorkspace Link` WHERE link_to = %s",
        dt_name,
    )
    frappe.db.sql(
        "DELETE FROM `tabWorkspace Shortcut` WHERE link_to = %s",
        dt_name,
    )

    # Also ensure the DocType DB record is gone (in case v1 patch was skipped)
    if frappe.db.exists("DocType", dt_name):
        frappe.db.sql("DELETE FROM `tabDocField` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocType` WHERE name = %s", dt_name)

    if frappe.db.table_exists(f"tab{dt_name}"):
        frappe.db.sql(f"DROP TABLE IF EXISTS `tab{dt_name}`")

    frappe.db.commit()
