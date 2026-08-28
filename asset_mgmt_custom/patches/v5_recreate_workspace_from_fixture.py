"""
Nuclear option: delete the workspace entirely from DB and re-insert it
from the fixture file on disk.

Previous patches (v1-v4) tried incremental SQL fixes but could not
guarantee a clean state because of complex interactions between
rename/delete logic and fixture sync ordering.

This patch:
1. Deletes ALL workspace records (and their child rows) where
   module = 'Asset Mgmt Custom'.
2. Reads workspace.json fixture from disk.
3. Re-inserts the workspace using frappe.get_doc().insert() with
   link/mandatory validation bypassed so stale link targets don't block.
4. Also removes the stale 'Asset Preventive Maintenance Schedule'
   DocType record and the 'Overdue PM Schedules' Number Card from DB.
"""
import json
import os

import frappe


def execute():
    module = "Asset Mgmt Custom"

    # ── 1. Delete all workspace records for this module ───────────────────────
    ws_names = frappe.db.sql(
        "SELECT name FROM `tabWorkspace` WHERE module = %s", module, as_list=True
    )
    ws_names = [r[0] for r in ws_names]

    for ws_name in ws_names:
        for tbl in ("tabWorkspace Link", "tabWorkspace Shortcut", "tabWorkspace Number Card"):
            frappe.db.sql(f"DELETE FROM `{tbl}` WHERE parent = %s", ws_name)
        frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name = %s", ws_name)
        print(f"Deleted workspace: {ws_name}")

    # ── 2. Read fixture from disk ─────────────────────────────────────────────
    fixture_path = os.path.join(
        frappe.get_app_path("asset_mgmt_custom"), "fixtures", "workspace.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        fixture_data = json.load(f)

    ws_data = fixture_data[0] if isinstance(fixture_data, list) else fixture_data

    # ── 3. Insert fresh workspace (bypass link + mandatory validation) ────────
    doc = frappe.get_doc(ws_data)
    doc.flags.ignore_links = True
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    print(f"Inserted workspace: {doc.name}")

    # ── 4. Clean up stale DocType and Number Card ─────────────────────────────
    dt = "Asset Preventive Maintenance Schedule"
    if frappe.db.exists("DocType", dt):
        for tbl in ("tabDocField", "tabDocPerm"):
            frappe.db.sql(f"DELETE FROM `{tbl}` WHERE parent = %s", dt)
        frappe.db.sql("DELETE FROM `tabDocType` WHERE name = %s", dt)
        print(f"Removed DocType: {dt}")

    old_card = "Overdue PM Schedules"
    if frappe.db.exists("Number Card", old_card):
        frappe.db.sql("DELETE FROM `tabNumber Card` WHERE name = %s", old_card)
        print(f"Removed Number Card: {old_card}")

    frappe.db.commit()
    print("v5 complete — workspace recreated cleanly.")
