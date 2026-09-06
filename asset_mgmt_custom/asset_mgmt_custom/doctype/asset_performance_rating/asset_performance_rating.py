import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, today

# الوصف الموثَّق على overall_rating يقول "يُحسب تلقائياً: متوسط جميع
# الدرجات" — لكن لا شيء كان يحسبه فعلياً؛ الحقل (رغم أنه reqd=1) كان
# يُختار يدوياً بمعزل تام عن الدرجات المُدخَلة. هذا الترتيب (الأعلى فالأدنى)
# يُنفِّذ الوعد الموثَّق فعلياً.
RATING_THRESHOLDS = [
    (8.5, "Excellent", "No Action Needed"),
    (7, "Good", "No Action Needed"),
    (5, "Fair", "Increase Monitoring"),
    (3, "Poor", "Plan Replacement"),
    (0, "Critical", "Immediate Action Required"),
]


class AssetPerformanceRating(Document):
    def validate(self):
        for field in ["performance_score", "reliability_score", "efficiency_score"]:
            val = self.get(field)
            if val is not None and (val < 1 or val > 10):
                frappe.throw(f"{field.replace('_', ' ').title()} must be between 1 and 10.")
        self._auto_calculate_overall()

    def _auto_calculate_overall(self):
        scores = [s for s in (self.performance_score, self.reliability_score, self.efficiency_score) if s is not None]
        if not scores:
            return
        avg = sum(scores) / len(scores)
        for threshold, rating, action in RATING_THRESHOLDS:
            if avg >= threshold:
                self.overall_rating = rating
                if not self.recommended_action:
                    self.recommended_action = action
                break

    @frappe.whitelist()
    def compute_from_health_data(self):
        """
        يملأ الدرجات الثلاث من بيانات محسوبة فعلياً بدل تقييم ذاتي بحت —
        هذا التطبيق يحسب بالفعل مؤشر صحة أصل مركَّب (AHI) أسبوعياً من
        نفس هذه المصادر (تكرار الأعطال، الحالة، الانحراف) — إعادة تخمين
        نفس الشيء يدوياً هنا كان تكراراً بلا داعٍ:
        - درجة الأداء: من custom_ahi_score (مقياس 0-100) محوَّلة لمقياس 1-10.
        - درجة الموثوقية: من عدد الأعطال الفعلية آخر 12 شهراً (Asset
          Failure Analysis) — نفس مصدر بيانات AHI نفسه.
        - درجة الكفاءة: من متوسط نسبة الاستخدام الفعلية آخر 90 يوماً
          (Asset Utilization Log).
        """
        if not self.asset:
            frappe.throw(_("Please set the Asset first."))

        ahi = frappe.db.get_value("Asset", self.asset, "custom_ahi_score")
        if ahi is None:
            frappe.throw(_(
                "Asset Health Index (AHI) has not been computed yet for this asset — "
                "wait for the next weekly refresh (refresh_asset_health_index)."
            ))
        self.performance_score = max(1, min(10, round(flt(ahi) / 10, 1)))

        failure_count = frappe.db.count(
            "Asset Failure Analysis",
            filters={"asset": self.asset, "failure_date": [">=", add_days(today(), -365)]},
        )
        self.reliability_score = max(1, min(10, round(10 - failure_count * 1.5, 1)))

        avg_util = frappe.db.sql("""
            SELECT AVG(utilization_pct) FROM `tabAsset Utilization Log`
            WHERE asset = %s AND log_date >= %s
        """, (self.asset, add_days(today(), -90)))[0][0]
        if avg_util is not None:
            self.efficiency_score = max(1, min(10, round(flt(avg_util) / 10, 1)))

        self._auto_calculate_overall()

        return {
            "performance_score": self.performance_score,
            "reliability_score": self.reliability_score,
            "efficiency_score": self.efficiency_score,
            "overall_rating": self.overall_rating,
            "recommended_action": self.recommended_action,
        }
