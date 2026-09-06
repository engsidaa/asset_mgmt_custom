import statistics

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
            breached = self._check_temperature_threshold()
            if not breached:
                self._check_temperature_drift()

    def _check_temperature_threshold(self):
        """
        مراقبة سلسلة التبريد (Cold Chain): قراءة حرارة خارج النطاق الآمن
        المحدَّد على فئة الأصل تُنشئ أمر عمل طارئ بأولوية 'حرج' تلقائياً —
        مسألة سلامة غذائية (فريزر/ثلاجة معطلة)، وليست رفاهية تحسين، فلا
        تنتظر ملاحظة يدوية من أحد.
        """
        if self.temperature_celsius is None or not self.asset:
            return False

        asset = frappe.db.get_value(
            "Asset", self.asset, ["asset_category", "asset_name", "custom_branch"], as_dict=True
        )
        if not asset or not asset.asset_category:
            return False

        limits = frappe.db.get_value(
            "Asset Category", asset.asset_category,
            ["custom_min_safe_temperature", "custom_max_safe_temperature"],
            as_dict=True,
        )
        if not limits:
            return False

        breached = False
        if limits.custom_min_safe_temperature is not None and flt(self.temperature_celsius) < flt(limits.custom_min_safe_temperature):
            breached = True
        if limits.custom_max_safe_temperature is not None and flt(self.temperature_celsius) > flt(limits.custom_max_safe_temperature):
            breached = True
        if not breached:
            return False

        already_open = frappe.db.exists("Asset Work Order", {
            "asset": self.asset,
            "work_type": "طارئ",
            "priority": "حرج",
            "docstatus": ["<", 2],
            "status": ["in", ["مفتوح", "قيد التنفيذ"]],
        })
        if already_open:
            return True

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
        return True

    def _check_temperature_drift(self):
        """
        كشف اتجاه تدريجي (SPC — Statistical Process Control خفيف) قبل
        أن تتجاوز القراءة الحد الآمن فعلياً — مكمِّل لـ
        _check_temperature_threshold الذي يكتشف الخرق الفعلي فقط بعد
        حدوثه (ولا يُشغَّل إطلاقاً لو الخرق الفعلي حدث بالفعل، لتفادي
        إنذارين لنفس المشكلة). قاعدتان كلاسيكيتان:

        1. انحراف حاد (3-Sigma) عن السلوك المعتاد لهذا الأصل تحديداً —
           القراءة الحالية تبعد أكثر من 3 انحرافات معيارية عن متوسط آخر
           10 قراءات سابقة (عطل مفاجئ في الحساس/التبريد، وليس تدهوراً
           تدريجياً).
        2. اتجاه مستمر في نفس الاتجاه لآخر 5 قراءات على التوالي (تدهور
           تدريجي حقيقي — مثال: عزل تبريد يتلف تدريجياً — حتى لو كل
           قراءة بمفردها لا تزال ضمن النطاق الآمن حتى الآن).
        """
        if self.temperature_celsius is None or not self.asset:
            return

        history = frappe.get_all(
            "Asset Meter Reading",
            filters={"asset": self.asset, "meter_type": "درجة الحرارة", "name": ["!=", self.name]},
            fields=["temperature_celsius"],
            order_by="reading_date desc",
            limit_page_length=10,
        )
        values = [flt(r.temperature_celsius) for r in history if r.temperature_celsius is not None]
        if len(values) < 5:
            return  # عيّنة غير كافية لحكم إحصائي ذي دلالة

        current = flt(self.temperature_celsius)
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)

        sigma_breach = stdev > 0 and abs(current - mean) > 3 * stdev

        recent = [current] + values[:4]  # الأحدث أولاً
        trending_up = all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))
        trending_down = all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))

        if not sigma_breach and not (trending_up or trending_down):
            return

        asset = frappe.db.get_value("Asset", self.asset, ["asset_name", "custom_branch"], as_dict=True)
        if not asset:
            return

        already_open = frappe.db.exists("Asset Work Order", {
            "asset": self.asset,
            "work_type": "فحص",
            "priority": "عاجل",
            "docstatus": ["<", 2],
            "status": ["in", ["مفتوح", "قيد التنفيذ"]],
        })
        if already_open:
            return

        if sigma_breach:
            reason = _("انحراف حاد عن السلوك المعتاد لهذا الأصل (خارج 3 انحرافات معيارية)")
        elif trending_up:
            reason = _("اتجاه تصاعدي مستمر لآخر 5 قراءات")
        else:
            reason = _("اتجاه تنازلي مستمر لآخر 5 قراءات")

        wo = frappe.new_doc("Asset Work Order")
        wo.title = _("إنذار مبكر — انحراف إحصائي في قراءات الحرارة: {0}").format(asset.asset_name or self.asset)
        wo.asset = self.asset
        wo.branch = asset.custom_branch
        wo.work_type = "فحص"
        wo.priority = "عاجل"
        wo.problem_description = _(
            "انحراف إحصائي في قراءات درجة الحرارة (لم تتجاوز الحد الآمن بعد): {0}. "
            "القراءة الحالية {1}°م، متوسط آخر {2} قراءة {3}°م. يستحق فحصاً فنياً مبكراً قبل تفاقم المشكلة."
        ).format(reason, current, len(values), round(mean, 2))

        try:
            wo.insert(ignore_permissions=True)
            frappe.msgprint(
                _("رُصد انحراف إحصائي في القراءات — أُنشئ أمر فحص مبكر: <a href='/app/asset-work-order/{0}'>{0}</a>").format(wo.name),
                alert=True, indicator="orange",
            )
        except Exception:
            frappe.log_error(title="Auto statistical-drift inspection Work Order failed", message=frappe.get_traceback())
