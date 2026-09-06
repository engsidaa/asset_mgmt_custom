import frappe
from frappe.model.document import Document


class AssetFailureAnalysis(Document):
    def validate(self):
        self._sync_work_order_link()

    def _sync_work_order_link(self):
        """مزامنة في الاتجاهين مع Asset Work Order.failure_analysis — أياً
        كان الطرف الذي رُبط منه أولاً (من هذا المستند أو من أمر العمل)."""
        if not self.work_order:
            return
        linked = frappe.db.get_value("Asset Work Order", self.work_order, "failure_analysis")
        if linked != self.name:
            frappe.db.set_value("Asset Work Order", self.work_order, "failure_analysis", self.name, update_modified=False)


@frappe.whitelist()
def get_suggested_remedies(failure_mode, problem_code=None, exclude=None):
    """
    قاعدة معرفة (FMEA-style) — بدل إنشاء قاموس أعطال (Fault Dictionary)
    كمستند مستقل منفصل، نعيد استخدام سجل Asset Failure Analysis الفعلي
    نفسه: يبحث عن أكثر رموز الإجراء التصحيحي (remedy_code) تكراراً في
    الحالات السابقة لنفس تركيبة (رمز المشكلة + رمز السبب الجذري) — وليس
    السبب الجذري وحده كما كان سابقاً، لأن نفس السبب قد يحتاج إجراءات
    مختلفة حسب مظهر العطل الخارجي (problem_code) — عبر كل الأصول، لتُقترَح
    على المحلِّل قبل كتابة تحليل جديد.
    """
    if not failure_mode:
        return []

    filters = {"failure_mode": failure_mode, "remedy_code": ["is", "set"]}
    if problem_code:
        filters["problem_code"] = problem_code
    if exclude:
        filters["name"] = ["!=", exclude]

    rows = frappe.get_all(
        "Asset Failure Analysis",
        filters=filters,
        fields=["remedy_code", "corrective_action", "name", "asset", "failure_date"],
        order_by="failure_date desc",
        limit_page_length=200,
    )

    counts = {}
    for row in rows:
        key = row.remedy_code
        if not key:
            continue
        if key not in counts:
            counts[key] = {
                "remedy_code": key,
                "count": 0,
                "last_used": row.failure_date,
                "example": row.name,
                "example_detail": row.corrective_action,
            }
        counts[key]["count"] += 1

    return sorted(counts.values(), key=lambda r: r["count"], reverse=True)[:10]
