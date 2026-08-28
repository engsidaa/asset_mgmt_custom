"""
Fix stale 'Overdue PM Schedules' reference in the workspace's number_cards
child table (tabWorkspace Number Card).

When build_workspace() processes number_cards, it does frappe.get_doc on each
card name. 'Overdue PM Schedules' was deleted from tabNumber Card in v3, but
the child table row still referenced it → DoesNotExistError → JS shows
"Workspace name not available".

This patch replaces the stale row with 'Open Asset Repairs' across ALL
workspaces so fixture sync doesn't have to do the heavy lifting alone.
"""
import frappe

OLD_CARD = "Overdue PM Schedules"
NEW_CARD = "Open Asset Repairs"


def execute():
    # Fix tabWorkspace Number Card rows
    frappe.db.sql(
        """
        UPDATE `tabWorkspace Number Card`
        SET number_card_name = %s
        WHERE number_card_name = %s
        """,
        (NEW_CARD, OLD_CARD),
    )
    rows = frappe.db.sql(
        "SELECT ROW_COUNT() AS n", as_dict=True
    )
    print(f"Updated {rows[0].get('n', '?')} Workspace Number Card rows: {OLD_CARD} → {NEW_CARD}")

    # Also clean up tabNumber Card if old record still exists
    if frappe.db.exists("Number Card", OLD_CARD):
        frappe.db.sql("DELETE FROM `tabNumber Card` WHERE name = %s", OLD_CARD)
        print(f"Deleted stale Number Card: {OLD_CARD}")

    # Ensure our workspace is public and not hidden
    frappe.db.sql(
        """
        UPDATE `tabWorkspace`
        SET `public` = 1, `is_hidden` = 0
        WHERE module = 'Asset Mgmt Custom'
        """,
    )

    frappe.db.commit()
    print("v4 complete.")
