import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

# مصفوفة الحرجية (Asset Criticality Matrix) كانت غير مربوطة بأي قرار
# تشغيلي فعلي — هذا هو أقصى فاصل مسموح بين فحصين للأصول الأعلى حرجية،
# بحيث لا يقدر أحد (سهواً) يحدِّد فحص السلامة القادم بعد 6 أشهر لأصل
# "حرج جداً".
CRITICALITY_MAX_INSPECTION_INTERVAL_DAYS = {
    "Critical": 30,
    "High": 90,
}


class AssetSafetyInspection(Document):
    def validate(self):
        if self.inspection_date and self.next_inspection_date:
            if self.next_inspection_date <= self.inspection_date:
                frappe.throw("Next Inspection Date must be after Inspection Date.")
        self._cap_next_inspection_by_criticality()
        self._require_photo_on_fail()

    def _cap_next_inspection_by_criticality(self):
        if not self.asset or not self.inspection_date or not self.next_inspection_date:
            return

        max_days = CRITICALITY_MAX_INSPECTION_INTERVAL_DAYS.get(
            frappe.db.get_value("Asset Criticality Matrix", {"asset": self.asset}, "criticality_level")
        )
        if not max_days:
            return

        max_allowed = add_days(self.inspection_date, max_days)
        if getdate(self.next_inspection_date) > getdate(max_allowed):
            self.next_inspection_date = max_allowed

    def _require_photo_on_fail(self):
        """توثيق حي إلزامي: أي بند فحص بنتيجة 'Fail' بلا صورة يُرفَض
        الحفظ — لا يُسمَح بتسجيل مخالفة سلامة بدون دليل مرئي فوري."""
        missing = [
            str(row.idx) for row in (self.items or [])
            if row.result == "Fail" and not row.photo
        ]
        if missing:
            frappe.throw(
                _("A documentation photo is required for every 'Fail' result. Missing on row(s): {0}").format(
                    ", ".join(missing)
                ),
                title=_("Photo Required"),
            )

    def on_update(self):
        self._create_corrective_work_orders()

    def _create_corrective_work_orders(self):
        """
        كل بند بنتيجة 'Fail' ولم يُنشأ له أمر عمل تصحيحي بعد، يُولِّد
        تلقائياً Asset Work Order بأولوية 'حرج' (مخالفة سلامة، لا تنتظر
        دورة الصيانة العادية) — واحد لكل بند فاشل، وليس واحداً للتفتيش
        بالكامل، لأن كل بند قد يحتاج فنياً/إجراءً مختلفاً تماماً.
        """
        if not self.asset:
            return

        for row in self.items or []:
            if row.result != "Fail" or row.get("corrective_work_order"):
                continue

            branch = frappe.db.get_value("Asset", self.asset, "custom_branch")
            wo = frappe.new_doc("Asset Work Order")
            wo.asset = self.asset
            wo.branch = branch
            wo.work_type = "إصلاح"
            wo.priority = "حرج"
            wo.request_date = today()
            wo.problem_description = _(
                "Auto-generated from a failed safety inspection item: '{0}' (inspection {1}). {2}"
            ).format(row.check_item, self.name, row.remarks or "")

            try:
                wo.insert(ignore_permissions=True)
                frappe.db.set_value(
                    "Asset Safety Inspection Item", row.name, "corrective_work_order", wo.name,
                    update_modified=False,
                )
            except Exception:
                frappe.log_error(
                    title="Auto corrective Work Order creation failed (Safety Inspection)",
                    message=frappe.get_traceback(),
                )
