import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

PRIORITY_MAP = {"Low": "عادي", "Medium": "متوسط", "High": "عاجل", "Urgent": "حرج"}
WORK_TYPE_MAP_SAFETY = "طارئ"
WORK_TYPE_MAP_DEFAULT = "إصلاح"


class AssetComplaint(Document):
    @frappe.whitelist()
    def escalate_to_work_order(self):
        """
        Asset Complaint كان "بابا أمامياً" مستقلاً بالكامل — أي مستخدم
        يسجِّل شكوى (Performance Issue/Damage/Noise/Safety Concern...)
        لكن لا شيء كان يحوِّلها فعلياً لأمر عمل صيانة رسمي؛ تبقى الشكوى
        مجرد سجل، وفريق الصيانة الفعلي (Asset Work Order) لا يراها أبداً
        إلا لو أنشأ أحد أمر عمل يدوياً بمعزل تام عنها.
        """
        if self.get("escalated_work_order"):
            frappe.throw(_("This complaint was already escalated to Work Order {0}.").format(
                self.escalated_work_order
            ))
        if self.status in ("Resolved", "Closed"):
            frappe.throw(_("Cannot escalate a complaint that is already {0}.").format(self.status))

        branch = frappe.db.get_value("Asset", self.asset, "custom_branch")
        wo = frappe.new_doc("Asset Work Order")
        wo.asset = self.asset
        wo.branch = branch
        wo.work_type = WORK_TYPE_MAP_SAFETY if self.complaint_type == "Safety Concern" else WORK_TYPE_MAP_DEFAULT
        wo.priority = PRIORITY_MAP.get(self.priority, "متوسط")
        wo.request_date = today()
        wo.problem_description = _("Escalated from Asset Complaint {0} ({1}): {2}").format(
            self.name, self.complaint_type or "-", frappe.utils.strip_html(self.description or "")
        )
        wo.insert(ignore_permissions=True)

        self.db_set("escalated_work_order", wo.name, update_modified=False)
        self.db_set("status", "In Progress", update_modified=False)

        return wo.name
