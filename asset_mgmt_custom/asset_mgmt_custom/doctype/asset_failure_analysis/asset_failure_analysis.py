import frappe
from frappe.model.document import Document


class AssetFailureAnalysis(Document):
    pass


@frappe.whitelist()
def get_suggested_remedies(failure_mode, exclude=None):
    """
    قاعدة معرفة بسيطة للحلول (Knowledge Base) — بدل إنشاء قاموس أعطال
    (Fault Dictionary) كمستند مستقل منفصل، نعيد استخدام سجل Asset Failure
    Analysis الفعلي نفسه: يبحث عن أكثر الإجراءات التصحيحية (corrective_action)
    تكراراً في الحالات السابقة لنفس نمط العطل (failure_mode)، عبر كل
    الأصول، لتُقترَح على المحلِّل قبل كتابة تحليل جديد.
    """
    if not failure_mode:
        return []

    filters = {"failure_mode": failure_mode, "corrective_action": ["is", "set"]}
    if exclude:
        filters["name"] = ["!=", exclude]

    rows = frappe.get_all(
        "Asset Failure Analysis",
        filters=filters,
        fields=["corrective_action", "name", "asset", "failure_date"],
        order_by="failure_date desc",
        limit_page_length=200,
    )

    counts = {}
    for row in rows:
        key = (row.corrective_action or "").strip()
        if not key:
            continue
        if key not in counts:
            counts[key] = {"corrective_action": key, "count": 0, "last_used": row.failure_date, "example": row.name}
        counts[key]["count"] += 1

    return sorted(counts.values(), key=lambda r: r["count"], reverse=True)[:10]
