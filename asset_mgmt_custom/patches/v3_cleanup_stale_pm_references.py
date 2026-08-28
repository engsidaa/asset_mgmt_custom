"""
Comprehensive cleanup of all stale 'Asset Preventive Maintenance Schedule'
and 'Overdue PM Schedules' references that cause DocType-not-found errors:

1. Delete the stale 'Overdue PM Schedules' Number Card from DB.
   (It was renamed to 'Open Asset Repairs' in fixtures but the old DB
    record with document_type='Asset Preventive Maintenance Schedule'
    remained and is the root cause of the error when the workspace loads.)

2. Patch the workspace content JSON in DB to replace any remaining
   reference to 'Overdue PM Schedules' with 'Open Asset Repairs'.

3. Rename the 'Asset Management' workspace to 'إدارة الأصول' in DB
   if an English-named orphan exists (fixture was renamed; old record stays).

4. Final sweep: delete any remaining Workspace Link / Shortcut rows
   pointing to the deleted DocType (belt-and-suspenders over v2 patch).

5. Ensure the DocType DB record is gone.
"""
import json
import frappe


def execute():
    dt_name = "Asset Preventive Maintenance Schedule"
    old_card = "Overdue PM Schedules"
    new_card = "Open Asset Repairs"
    old_ws_name = "Asset Management"      # English orphan from previous fixture
    new_ws_name = "إدارة الأصول"           # Correct name matching URL /إدارة-الأصول

    # ── 1. Delete stale number card ───────────────────────────────────────────
    if frappe.db.exists("Number Card", old_card):
        frappe.db.sql("DELETE FROM `tabNumber Card` WHERE name = %s", old_card)
        print(f"Deleted stale Number Card: {old_card}")

    # ── 2. Fix workspace content in ALL workspace records ─────────────────────
    rows = frappe.db.sql(
        "SELECT name, content FROM `tabWorkspace` WHERE content LIKE %s",
        f"%{old_card}%",
        as_dict=True,
    )
    for row in rows:
        if not row.content:
            continue
        try:
            fixed = row.content.replace(old_card, new_card)
            frappe.db.sql(
                "UPDATE `tabWorkspace` SET content = %s WHERE name = %s",
                (fixed, row.name),
            )
            print(f"Fixed content in workspace: {row.name}")
        except Exception:
            pass

    # ── 3. Rename English-named orphan workspace to Arabic name ───────────────
    if frappe.db.exists("Workspace", old_ws_name) and not frappe.db.exists(
        "Workspace", new_ws_name
    ):
        frappe.db.sql(
            "UPDATE `tabWorkspace` SET name = %s WHERE name = %s",
            (new_ws_name, old_ws_name),
        )
        # Update child table rows that reference parent by name
        for tbl in ("tabWorkspace Link", "tabWorkspace Shortcut"):
            frappe.db.sql(
                f"UPDATE `{tbl}` SET parent = %s WHERE parent = %s",
                (new_ws_name, old_ws_name),
            )
        print(f"Renamed workspace '{old_ws_name}' → '{new_ws_name}'")
    elif frappe.db.exists("Workspace", old_ws_name) and frappe.db.exists(
        "Workspace", new_ws_name
    ):
        # Both exist; delete the English orphan
        frappe.db.sql(
            "DELETE FROM `tabWorkspace Link` WHERE parent = %s", old_ws_name
        )
        frappe.db.sql(
            "DELETE FROM `tabWorkspace Shortcut` WHERE parent = %s", old_ws_name
        )
        frappe.db.sql(
            "DELETE FROM `tabWorkspace` WHERE name = %s", old_ws_name
        )
        print(f"Deleted orphan workspace '{old_ws_name}' ('{new_ws_name}' exists)")

    # ── 4. Final sweep: remove all workspace links pointing to deleted DocType ─
    frappe.db.sql(
        "DELETE FROM `tabWorkspace Link` WHERE link_to = %s", dt_name
    )
    frappe.db.sql(
        "DELETE FROM `tabWorkspace Shortcut` WHERE link_to = %s", dt_name
    )

    # ── 5. Ensure DocType DB record is gone ───────────────────────────────────
    if frappe.db.exists("DocType", dt_name):
        frappe.db.sql("DELETE FROM `tabDocField` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent = %s", dt_name)
        frappe.db.sql("DELETE FROM `tabDocType` WHERE name = %s", dt_name)
        if frappe.db.table_exists(f"tab{dt_name}"):
            frappe.db.sql(f"DROP TABLE IF EXISTS `tab{dt_name}`")
        print(f"Removed DocType DB record: {dt_name}")

    frappe.db.commit()
    print("v3 cleanup complete.")
