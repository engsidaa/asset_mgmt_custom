import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AssetMeterReading(Document):
    def before_save(self):
        if self.meter_type == "درجة الحرارة":
            self.previous_reading = 0
            self.units_consumed = 0
            return

        # Get previous reading for this asset and meter type
        prev = frappe.db.sql("""
            SELECT current_reading FROM `tabAsset Meter Reading`
            WHERE asset = %s AND meter_type = %s AND name != %s
            ORDER BY reading_date DESC, creation DESC LIMIT 1
        """, (self.asset, self.meter_type, self.name or ""))
        self.previous_reading = prev[0][0] if prev else 0
        consumed = (self.current_reading or 0) - (self.previous_reading or 0)
        self.units_consumed = max(consumed, 0)

    def after_insert(self):
        if self.meter_type == "درجة الحرارة":
            self._check_temperature_threshold()

    def _check_temperature_threshold(self):
        """
        مراقبة سلسلة التبريد (Cold Chain): قراءة حرارة خارج النطاق الآمن
        المحدَّد على فئة الأصل تُنشئ أمر عمل طارئ بأولوية 'حرج' تلقائياً —
        مسألة سلامة غذائية (فريزر/ثلاجة معطلة)، وليست رفاهية تحسين، فلا
        تنتظر ملاحظة يدوية من أحد.
        """
        if self.temperature_celsius is None or not self.asset:
            return

        asset = frappe.db.get_value(
            "Asset", self.asset, ["asset_category", "asset_name", "custom_branch"], as_dict=True
        )
        if not asset or not asset.asset_category:
            return

        limits = frappe.db.get_value(
            "Asset Category", asset.asset_category,
            ["custom_min_safe_temperature", "custom_max_safe_temperature"],
            as_dict=True,
        )
        if not limits:
            return

        breached = False
        if limits.custom_min_safe_temperature is not None and flt(self.temperature_celsius) < flt(limits.custom_min_safe_temperature):
            breached = True
        if limits.custom_max_safe_temperature is not None and flt(self.temperature_celsius) > flt(limits.custom_max_safe_temperature):
            breached = True
        if not breached:
            return

        already_open = frappe.db.exists("Asset Work Order", {
            "asset": self.asset,
            "work_type": "طارئ",
            "priority": "حرج",
            "docstatus": ["<", 2],
            "status": ["in", ["مفتوح", "قيد التنفيذ"]],
        })
        if already_open:
            return

        wo = frappe.new_doc("Asset Work Order")
        wo.title = _("تنبيه حرارة حرج: {0}").format(asset.asset_name or self.asset)
        wo.asset = self.asset
        wo.branch = asset.custom_branch
        wo.work_type = "طارئ"
        wo.priority = "حرج"
        wo.problem_description = _(
            "خرق نطاق درجة الحرارة الآمن لسلسلة التبريد: القراءة المسجلة {0}°م بتاريخ {1} "
            "(النطاق الآمن: {2}°م إلى {3}°م). يتطلب فحصاً فورياً."
        ).format(
            self.temperature_celsius, self.reading_date,
            limits.custom_min_safe_temperature, limits.custom_max_safe_temperature,
        )
        wo.insert(ignore_permissions=True)

        frappe.msgprint(
            _("تم إنشاء أمر عمل طارئ تلقائياً: <a href='/app/asset-work-order/{0}'>{0}</a>").format(wo.name),
            alert=True, indicator="red",
        )
