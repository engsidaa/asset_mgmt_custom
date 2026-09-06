import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

APPROVER_ROLES = ("Asset Manager", "System Manager")


class AssetTransferRequest(Document):
    def validate(self):
        if self.from_branch and self.to_branch and self.from_branch == self.to_branch:
            frappe.throw("From Branch and To Branch cannot be the same.")

    def on_submit(self):
        self.db_set("status", "Pending")

    def on_cancel(self):
        self.db_set("status", "Pending")

    def _check_approver(self):
        if not set(frappe.get_roles()) & set(APPROVER_ROLES):
            frappe.throw(_("You are not authorized to act on this request."), frappe.PermissionError)

    @frappe.whitelist()
    def approve(self):
        self._check_approver()
        if self.status != "Pending":
            frappe.throw(_("This request is not pending approval."))
        self.db_set("approved_by", frappe.session.user, update_modified=False)
        self.db_set("status", "Approved", update_modified=False)

    @frappe.whitelist()
    def reject(self, reason):
        self._check_approver()
        if self.status != "Pending":
            frappe.throw(_("This request is not pending approval."))
        if not reason or not reason.strip():
            frappe.throw(_("Please provide a rejection reason."))
        self.db_set("rejection_reason", reason, update_modified=False)
        self.db_set("status", "Rejected", update_modified=False)

    @frappe.whitelist()
    def execute_transfer(self):
        """
        الموافقة (Approved) كانت قراراً إدارياً فقط بلا أي أثر فعلي —
        الأصل يبقى في مكانه القديم للأبد رغم "الموافقة"، ولا شيء يربط
        هذا الطلب بحركة Asset Movement حقيقية. يُنشئ الحركة الفعلية
        (Transfer) من بيانات الطلب نفسه — تحديث الفرع/مركز التكلفة/سجل
        تاريخ المواقع يحدث تلقائياً عبر overrides/asset_movement.py
        الموجود بالفعل، بلا تكرار أي من ذلك هنا.
        """
        self._check_approver()
        if self.status != "Approved":
            frappe.throw(_("This request must be Approved before executing the transfer."))
        if self.get("asset_movement"):
            frappe.throw(_("Transfer already executed via {0}.").format(self.asset_movement))

        to_location = frappe.db.get_value("Branch", self.to_branch, "custom_default_location")
        if not to_location:
            frappe.throw(_("Branch {0} has no Default Location set — set one first.").format(self.to_branch))

        asset = frappe.get_doc("Asset", self.asset)

        mv = frappe.new_doc("Asset Movement")
        mv.purpose = "Transfer"
        mv.company = asset.company
        mv.transaction_date = self.transfer_date or today()
        mv.append("assets", {
            "asset": self.asset,
            "source_location": asset.location,
            "target_location": to_location,
            "custom_target_branch": self.to_branch,
            "from_employee": self.employee,
        })
        mv.insert(ignore_permissions=True)
        mv.submit()

        self.db_set("asset_movement", mv.name, update_modified=False)
        self.db_set("status", "Completed", update_modified=False)
        return mv.name
