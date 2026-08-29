"""
after_migrate hooks — run AFTER sync_fixtures(), unlike patches.txt entries
which run before it. Needed for anything that touches a DB column created
by a Custom Field fixture in the same deploy.
"""
import frappe


def unify_asset_manager_role():
    """
    The app had two roles doing the same job: 'Asset Manager' (singular —
    matches the deliberate 5-role naming convention: Asset User, Asset
    Technician, Asset Manager, Asset Finance Manager, System Manager) and
    'Assets Manager' (plural). Both were granted permissions in parallel
    across all 59+ doctypes, and in some doctypes 'Assets Manager' actually
    had BROADER permissions (submit/cancel/amend/report/export/print/email)
    that 'Asset Manager' lacked — a real, verified mismatch, not just a
    naming typo. All fixtures (DocType permissions, Report roles, Workflow
    allowed/state-edit roles) and code (notification queries, JS role
    checks) have been updated to the union of both roles' permissions,
    consolidated under 'Asset Manager' only.

    That fixture cleanup does not touch the live `tabRole` record or any
    user's actual role assignment. This does: frappe.rename_doc with
    merge=True updates every Link field across the system that points to
    the old Role — including Has Role (so any user who had 'Assets
    Manager' keeps their access, now under 'Asset Manager') — then removes
    the now-empty duplicate. Whichever of the two roles real users
    actually held before this deploy, they lose nothing.
    """
    old_role = "Assets Manager"
    new_role = "Asset Manager"

    if not frappe.db.exists("Role", old_role):
        return

    try:
        if frappe.db.exists("Role", new_role):
            frappe.rename_doc("Role", old_role, new_role, merge=True, force=True)
        else:
            frappe.rename_doc("Role", old_role, new_role, force=True)
        frappe.db.commit()
        print(f"Unified role: '{old_role}' -> '{new_role}'")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="unify_asset_manager_role failed")


def backfill_asset_coding_status():
    """
    custom_coding_status (added alongside the before/after tagging photos)
    didn't exist before. Any asset already Operational — or already tagged
    with a photo under the old single-photo field — must have passed the
    old tag+photo gate in set_operational(), so it's retroactively Coded
    rather than left at the new default of Uncoded.

    Safe to run on every migrate: only touches rows still missing a value.
    """
    if not frappe.db.has_column("Asset", "custom_coding_status"):
        return

    frappe.db.sql(
        """
        UPDATE `tabAsset`
        SET custom_coding_status = 'Coded'
        WHERE custom_operational_status = 'Operational'
          AND (custom_coding_status IS NULL OR custom_coding_status = '')
        """
    )

    frappe.db.sql(
        """
        UPDATE `tabAsset`
        SET custom_coding_status = 'Coded'
        WHERE custom_tag_type IS NOT NULL AND custom_tag_type != ''
          AND custom_tagging_photo IS NOT NULL AND custom_tagging_photo != ''
          AND (custom_coding_status IS NULL OR custom_coding_status = '')
        """
    )

    frappe.db.sql(
        """
        UPDATE `tabAsset`
        SET custom_coding_status = 'Uncoded'
        WHERE custom_coding_status IS NULL OR custom_coding_status = ''
        """
    )

    frappe.db.commit()


def remove_old_asset_requisition_workflow():
    """
    Asset Requisition's approval used to be a single-step Frappe Workflow
    (states: Draft/Pending Approval/Approved/Rejected/Fulfilled, one
    'Assets Manager' gate). It's replaced by a real 3-step approval chain
    (Finance -> Branch Manager -> Asset Manager) implemented directly on
    the doctype's own status field + whitelisted methods — Frappe's
    Workflow engine only supports role-based gates, not "the specific
    person assigned to this record's branch", which the 2nd step needs.

    Removing "Asset Requisition Approval" from the fixture does NOT
    delete the existing Workflow record from the DB — fixture sync only
    adds/updates, never deletes. Left in place, it would keep validating
    `status` against its own old state list and conflict with the new
    values. This deletes it explicitly, and remaps any document still
    sitting on the old "Pending Approval" status (which no longer exists
    as a valid option) back to the start of the new chain.
    """
    old_workflow = "Asset Requisition Approval"
    if frappe.db.exists("Workflow", old_workflow):
        frappe.db.sql("DELETE FROM `tabWorkflow Document State` WHERE parent = %s", old_workflow)
        frappe.db.sql("DELETE FROM `tabWorkflow Transition` WHERE parent = %s", old_workflow)
        frappe.db.sql("DELETE FROM `tabWorkflow` WHERE name = %s", old_workflow)
        print(f"Removed obsolete Workflow: {old_workflow}")

    if frappe.db.has_column("Asset Requisition", "status"):
        frappe.db.sql(
            """
            UPDATE `tabAsset Requisition`
            SET status = 'Pending Finance Approval'
            WHERE status = 'Pending Approval'
            """
        )

    frappe.db.commit()
