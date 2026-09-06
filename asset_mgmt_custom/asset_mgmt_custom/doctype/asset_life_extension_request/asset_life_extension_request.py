import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, getdate, today


class AssetLifeExtensionRequest(Document):
    def validate(self):
        self._fetch_current_expected_disposal_date()

    def on_submit(self):
        self.db_set("status", "Approved")
        self._escalate_to_asset_repair()

    def on_cancel(self):
        self.db_set("status", "Pending")

    def _fetch_current_expected_disposal_date(self):
        """
        الأصل ليس له حقل "تاريخ التخلص المتوقع" مباشر — يُحسَب من نفس
        بيانات Finance Book المستخدمة أصلاً في refresh_asset_health_index
        (tasks.py._asset_remaining_life): تاريخ بدء الاستخدام + (عدد
        فترات الإهلاك × تكرارها بالأشهر) = تاريخ الاستهلاك الكامل
        المتوقع. لا يُعاد حسابه لو أُدخل يدوياً بالفعل.
        """
        if self.current_expected_disposal_date or not self.asset:
            return

        asset = frappe.db.get_value(
            "Asset", self.asset, ["available_for_use_date", "calculate_depreciation"], as_dict=True
        )
        if not asset or not asset.calculate_depreciation or not asset.available_for_use_date:
            return

        fb = frappe.db.sql("""
            SELECT total_number_of_depreciations, frequency_of_depreciation
            FROM `tabAsset Finance Book`
            WHERE parent = %s AND parenttype = 'Asset'
            ORDER BY idx ASC LIMIT 1
        """, self.asset, as_dict=True)
        if not fb or not fb[0].total_number_of_depreciations:
            return

        total_months = cint(fb[0].total_number_of_depreciations) * cint(fb[0].frequency_of_depreciation)
        self.current_expected_disposal_date = add_months(getdate(asset.available_for_use_date), total_months)

    def _escalate_to_asset_repair(self):
        """
        الموافقة على تمديد العمر الإنتاجي (submit = Approved، بنفس منطق
        on_submit الحالي) كانت تُسجِّل القرار فقط بلا أي أثر محاسبي أو
        فعلي على جدول إهلاك الأصل — الأصل يبقى بنفس عمره الإنتاجي القديم
        رغم "الموافقة". آلية تمديد العمر الإنتاجي الصحيحة والكاملة
        (رسملة + إعادة جدولة إهلاك) موجودة بالفعل في Asset Repair
        (capitalize_repair_cost + increase_in_asset_life — انظر
        overrides/asset_repair.py وAsset Work Order._escalate_to_asset_repair
        لنفس النمط بالضبط) — بدل تكرارها هنا، تُنشأ وتُسلَّم Asset Repair
        حقيقية من بيانات هذا الطلب.
        """
        if self.get("resulting_asset_repair"):
            return

        asset = frappe.get_doc("Asset", self.asset)
        repair = frappe.new_doc("Asset Repair")
        repair.asset = self.asset
        repair.company = asset.company
        repair.failure_date = self.request_date or today()
        repair.completion_date = today()
        repair.repair_status = "Completed"
        repair.description = self.justification
        repair.custom_repair_notes = self.condition_report
        repair.repair_cost = flt(self.estimated_extension_cost)
        repair.capitalize_repair_cost = 1
        repair.increase_in_asset_life = cint(flt(self.requested_extension_years) * 12)
        repair.cost_center = asset.get("cost_center")
        repair.insert(ignore_permissions=True)
        repair.submit()

        self.db_set("resulting_asset_repair", repair.name, update_modified=False)
        frappe.msgprint(
            _("تم تمديد العمر الإنتاجي فعلياً عبر Asset Repair {0} — راجع جدول الإهلاك المُحدَّث.").format(
                repair.name
            ),
            alert=True, indicator="green",
        )
