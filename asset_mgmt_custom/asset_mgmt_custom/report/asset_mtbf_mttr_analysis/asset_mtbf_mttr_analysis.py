"""
Asset MTBF/MTTR Analysis
Mean Time Between Failures (متوسط الوقت بين الأعطال)
Mean Time To Repair (متوسط وقت الإصلاح)

المصدر: Asset Repair + Asset Work Order (التصحيحية فقط) معاً — Asset
Repair وحدها كانت تُغفِل الغالبية الساحقة من الأعطال الفعلية، لأن أغلب
الصيانة التصحيحية اليومية تمر عبر Asset Work Order (المستخدَم في تطبيق
الموبايل)، لا Asset Repair (نادراً ما يُنشأ إلا مباشرة أو عبر رسملة
عمرة كبرى). عمود downtime تحديداً استُبدل بـ custom_downtime_hours
(الحقل الرقمي الفعلي) لأن downtime الأساسي حقل نصي لا شيء يملؤه
تلقائياً؛ وdowntime_hours على Asset Work Order (مُحتسَب تلقائياً عند
الإتمام) هو المصدر الوحيد الموثوق فعلياً لغالبية الأعطال.
"""
import frappe
from frappe import _
from frappe.utils import flt, date_diff, add_days


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "asset", "label": _("الأصل"), "fieldtype": "Link", "options": "Asset", "width": 160},
        {"fieldname": "asset_name", "label": _("اسم الأصل"), "fieldtype": "Data", "width": 200},
        {"fieldname": "asset_category", "label": _("الفئة"), "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"fieldname": "failure_count", "label": _("عدد الأعطال"), "fieldtype": "Int", "width": 110},
        {"fieldname": "total_downtime", "label": _("إجمالي وقت التوقف (ساعة)"), "fieldtype": "Float", "precision": 1, "width": 160},
        {"fieldname": "total_repair_cost", "label": _("إجمالي تكلفة الإصلاح"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "mtbf_days", "label": _("MTBF (يوم)"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "mttr_hours", "label": _("MTTR (ساعة)"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "availability_pct", "label": _("معدل التوافر %"), "fieldtype": "Percent", "width": 120},
        {"fieldname": "reliability_class", "label": _("تصنيف الموثوقية"), "fieldtype": "Data", "width": 130},
        {"fieldname": "last_failure", "label": _("آخر عطل"), "fieldtype": "Date", "width": 110},
    ]


def get_data(filters):
    repair_conditions = "WHERE r.docstatus = 1"
    wo_conditions = "WHERE wo.docstatus = 1 AND wo.status = 'مكتمل' AND IFNULL(wo.is_preventive_maintenance, 0) = 0"
    params = {}

    if filters.get("company"):
        repair_conditions += " AND a.company = %(company)s"
        wo_conditions += " AND a.company = %(company)s"
        params["company"] = filters["company"]
    if filters.get("asset_category"):
        repair_conditions += " AND a.asset_category = %(asset_category)s"
        wo_conditions += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]
    if filters.get("from_date"):
        repair_conditions += " AND r.failure_date >= %(from_date)s"
        wo_conditions += " AND DATE(wo.creation) >= %(from_date)s"
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        repair_conditions += " AND r.failure_date <= %(to_date)s"
        wo_conditions += " AND DATE(wo.creation) <= %(to_date)s"
        params["to_date"] = filters["to_date"]

    raw = frappe.db.sql(f"""
        SELECT
            asset,
            asset_name,
            asset_category,
            purchase_date,
            COUNT(*) AS failure_count,
            SUM(downtime) AS total_downtime,
            SUM(cost) AS total_repair_cost,
            MIN(failure_date) AS first_failure,
            MAX(failure_date) AS last_failure
        FROM (
            SELECT
                r.asset AS asset, a.asset_name, a.asset_category, a.purchase_date,
                r.failure_date AS failure_date,
                IFNULL(r.custom_downtime_hours, 0) AS downtime,
                IFNULL(r.repair_cost, 0) AS cost
            FROM `tabAsset Repair` r
            JOIN `tabAsset` a ON a.name = r.asset
            {repair_conditions}

            UNION ALL

            SELECT
                wo.asset AS asset, a.asset_name, a.asset_category, a.purchase_date,
                DATE(wo.creation) AS failure_date,
                IFNULL(wo.downtime_hours, 0) AS downtime,
                IFNULL(NULLIF(wo.actual_cost, 0), IFNULL(wo.labor_cost, 0)) AS cost
            FROM `tabAsset Work Order` wo
            JOIN `tabAsset` a ON a.name = wo.asset
            {wo_conditions}
        ) combined
        GROUP BY asset
        ORDER BY failure_count DESC
    """, params, as_dict=True)

    result = []
    for row in raw:
        failure_count = int(row.failure_count or 0)
        total_downtime = flt(row.total_downtime)

        # MTBF = (observation_period_days) / (failure_count - 1) or period / failure_count
        # Use span from first to last failure, or from purchase date to last failure
        start_date = row.first_failure or row.purchase_date
        end_date = row.last_failure
        if start_date and end_date:
            period_days = max(date_diff(end_date, start_date), 1)
        else:
            period_days = 365  # fallback

        # MTBF in days: time between failures
        mtbf_days = flt(period_days / max(failure_count, 1), 1)

        # MTTR in hours: average repair time
        mttr_hours = flt(total_downtime / max(failure_count, 1), 1)

        # Availability = MTBF / (MTBF + MTTR_days)
        mttr_days = mttr_hours / 24
        availability_pct = 0
        if mtbf_days + mttr_days > 0:
            availability_pct = flt((mtbf_days / (mtbf_days + mttr_days)) * 100, 1)

        # Reliability classification
        if availability_pct >= 98:
            reliability_class = "ممتاز ≥98%"
        elif availability_pct >= 95:
            reliability_class = "جيد ≥95%"
        elif availability_pct >= 90:
            reliability_class = "مقبول ≥90%"
        elif availability_pct >= 80:
            reliability_class = "ضعيف ≥80%"
        else:
            reliability_class = "حرج <80%"

        result.append({
            "asset": row.asset,
            "asset_name": row.asset_name,
            "asset_category": row.asset_category,
            "failure_count": failure_count,
            "total_downtime": total_downtime,
            "total_repair_cost": flt(row.total_repair_cost),
            "mtbf_days": mtbf_days,
            "mttr_hours": mttr_hours,
            "availability_pct": availability_pct,
            "reliability_class": reliability_class,
            "last_failure": row.last_failure,
        })

    return result


def get_chart(data):
    if not data:
        return None
    top10 = sorted(data, key=lambda x: x["mtbf_days"])[:10]
    return {
        "data": {
            "labels": [d["asset_name"][:20] for d in top10],
            "datasets": [
                {"name": "MTBF (يوم)", "values": [d["mtbf_days"] for d in top10]},
                {"name": "MTTR (ساعة)", "values": [d["mttr_hours"] for d in top10]},
            ],
        },
        "type": "bar",
        "colors": ["#3B82F6", "#F43F5E"],
        "title": "أقل 10 أصول موثوقية — MTBF vs MTTR",
    }


def get_summary(data):
    if not data:
        return []
    total_failures = sum(d["failure_count"] for d in data)
    avg_mtbf = flt(sum(d["mtbf_days"] for d in data) / max(len(data), 1), 1)
    avg_mttr = flt(sum(d["mttr_hours"] for d in data) / max(len(data), 1), 1)
    avg_avail = flt(sum(d["availability_pct"] for d in data) / max(len(data), 1), 1)
    return [
        {"label": _("إجمالي الأعطال"), "value": total_failures, "indicator": "Red"},
        {"label": _("متوسط MTBF (يوم)"), "value": avg_mtbf, "indicator": "Blue"},
        {"label": _("متوسط MTTR (ساعة)"), "value": avg_mttr, "indicator": "Orange"},
        {"label": _("متوسط معدل التوافر"), "value": f"{avg_avail}%", "indicator": "Green" if avg_avail >= 95 else "Orange"},
    ]
