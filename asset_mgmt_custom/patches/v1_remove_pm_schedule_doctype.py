"""
Remove stale Asset Preventive Maintenance Schedule DocType from DB.
This DocType was deleted from disk (true duplicate of ERPNext Asset Maintenance).
"""
import frappe


def execute():
    dt_name = "Asset Preventive Maintenance Schedule"

    # Remove the DocType record and all its field records
    if frappe.db.exists("DocType", dt_name):
        frappe.db.sql("DELETE FROM `tabDocField` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocType` WHERE name = %s", dt_name)

    # Drop the DB table if it still exists
    if frappe.db.table_exists(f"tab{dt_name}"):
        frappe.db.sql(f"DROP TABLE IF EXISTS `tab{dt_name}`")

    # Remove Workspace links and shortcuts pointing to this DocType
    ws_name = "Asset Mgmt Custom"
    if frappe.db.exists("Workspace", ws_name):
        frappe.db.sql("""
            DELETE FROM `tabWorkspace Link`
            WHERE parent = %s AND link_to = %s
        """, (ws_name, dt_name))
        frappe.db.sql("""
            DELETE FROM `tabWorkspace Shortcut`
            WHERE parent = %s AND link_to = %s
        """, (ws_name, dt_name))

    frappe.db.commit()
