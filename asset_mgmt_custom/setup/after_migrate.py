"""
after_migrate hooks — run AFTER sync_fixtures(), unlike patches.txt entries
which run before it. Needed for anything that touches a DB column created
by a Custom Field fixture in the same deploy.
"""
import frappe


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
