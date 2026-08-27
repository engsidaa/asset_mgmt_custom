import frappe
from frappe.model.document import Document


class AssetDisposalExecution(Document):
    def on_submit(self):
        self.db_set("disposal_status", "Executed")
        if self.disposal_request:
            frappe.db.set_value(
                "Asset Disposal Request",
                self.disposal_request,
                "workflow_state",
                "Approved",
                update_modified=False
            )

    def on_cancel(self):
        self.db_set("disposal_status", "Cancelled")
