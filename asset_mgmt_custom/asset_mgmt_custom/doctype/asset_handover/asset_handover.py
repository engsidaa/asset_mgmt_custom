import frappe
from frappe.model.document import Document
from frappe import _


class AssetHandover(Document):
    def validate(self):
        self._compute_summary()

    def on_submit(self):
        self.status = "Completed"
        self.db_set("status", "Completed")
        self._log_asset_activities()

    def _compute_summary(self):
        items = self.items or []
        self.total_assets = len(items)
        self.good_count = sum(1 for i in items if i.condition in ("Good", ""))
        self.damaged_count = sum(1 for i in items if i.condition == "Damaged")

    def _log_asset_activities(self):
        for item in self.items:
            if not item.asset:
                continue
            try:
                frappe.get_doc({
                    "doctype": "Asset Activity",
                    "asset": item.asset,
                    "activity_type": "Transfer",
                    "transaction_date": self.handover_date,
                    "reference_doctype": "Asset Handover",
                    "reference_docname": self.name,
                    "notes": _("Handover from {0} to {1} at branch {2}. Condition: {3}").format(
                        self.outgoing_manager, self.incoming_manager,
                        self.branch, item.condition or "Good"
                    ),
                }).insert(ignore_permissions=True)
            except Exception:
                pass


@frappe.whitelist()
def fetch_branch_assets(branch):
    return frappe.db.sql("""
        SELECT name, asset_name, asset_category, serial_no
        FROM `tabAsset`
        WHERE custom_branch = %(branch)s
          AND docstatus < 2
          AND status NOT IN ('Scrapped', 'Sold')
        ORDER BY asset_category, asset_name
    """, {"branch": branch}, as_dict=True)
