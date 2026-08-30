import frappe
from frappe.model.document import Document


class AssetDisposalExecution(Document):
    def on_submit(self):
        self.db_set("disposal_status", "Executed")
        if self.disposal_request:
            # "Asset Disposal Request" ماله حقل اسمه workflow_state —
            # حقل حالته الحقيقي هو status (Draft/Pending Approval/Approved/
            # Rejected، مفيش حالة "Executed" أصلاً هناك — التنفيذ متتبَّع
            # بالكامل في disposal_status هنا). كان هيفشل بخطأ SQL خام أول
            # ما ينفَّذ أي تصرف.
            frappe.db.set_value(
                "Asset Disposal Request",
                self.disposal_request,
                "status",
                "Approved",
                update_modified=False
            )

    def on_cancel(self):
        self.db_set("disposal_status", "Cancelled")
