import frappe
from frappe import _
from frappe.model.document import Document


class AssetEnvironmentalLog(Document):
    def on_update(self):
        self._create_corrective_work_order_if_non_compliant()

    def _create_corrective_work_order_if_non_compliant(self):
        """
        مخالفة بيئية (ISO 14001/50001 أو لائحة محلية) لم تكن تُنشئ أي أثر
        تشغيلي فعلي — is_compliant=0 كان يُسجَّل ولا يحدث بعده شيء، خلافاً
        لبند "Fail" في Asset Safety Inspection الذي يُنشئ أمر عمل تصحيحي
        تلقائياً بالفعل. نفس المنطق هنا الآن.
        """
        if self.is_compliant or self.get("corrective_work_order") or not self.asset:
            return

        branch = frappe.db.get_value("Asset", self.asset, "custom_branch")
        wo = frappe.new_doc("Asset Work Order")
        wo.asset = self.asset
        wo.branch = branch
        wo.work_type = "إصلاح"
        wo.priority = "عاجل"
        wo.problem_description = _(
            "مخالفة بيئية غير ممتثلة (المعيار: {0}): {1}"
        ).format(self.compliance_standard or "-", self.non_compliance_details or "")

        try:
            wo.insert(ignore_permissions=True)
            self.db_set("corrective_work_order", wo.name, update_modified=False)
            frappe.msgprint(
                _("تم إنشاء أمر عمل تصحيحي تلقائياً: <a href='/app/asset-work-order/{0}'>{0}</a>").format(wo.name),
                alert=True, indicator="orange",
            )
        except Exception:
            frappe.log_error(
                title="Auto corrective Work Order failed (Environmental Log)",
                message=frappe.get_traceback(),
            )
