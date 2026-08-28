"""
Asset OEE Report — Overall Equipment Effectiveness
فعالية المعدات الشاملة
OEE = Availability × Performance × Quality
Source: Asset Utilization Log + Asset Repair (downtime)
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "asset", "label": _("الأصل"), "fieldtype": "Link", "options": "Asset", "width": 150},
        {"fieldname": "asset_name", "label": _("اسم الأصل"), "fieldtype": "Data", "width": 200},
        {"fieldname": "asset_category", "label": _("الفئة"), "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"fieldname": "planned_hours", "label": _("ساعات التشغيل المخططة"), "fieldtype": "Float", "precision": 1, "width": 150},
        {"fieldname": "actual_hours", "label": _("ساعات التشغيل الفعلية"), "fieldtype": "Float", "precision": 1, "width": 150},
        {"fieldname": "downtime_hours", "label": _("ساعات التوقف"), "fieldtype": "Float", "precision": 1, "width": 120},
        {"fieldname": "availability_pct", "label": _("التوافر %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "performance_pct", "label": _("الأداء %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "quality_pct", "label": _("الجودة %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "oee_pct", "label": _("OEE %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "oee_class", "label": _("التصنيف"), "fieldtype": "Data", "width": 120},
    ]


def get_data(filters):
    conditions = "WHERE ul.docstatus = 1"
    params = {}

    if filters.get("from_date"):
        conditions += " AND ul.date >= %(from_date)s"
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND ul.date <= %(to_date)s"
        params["to_date"] = filters["to_date"]
    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]
    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        params["company"] = filters["company"]

    util_data = frappe.db.sql(f"""
        SELECT
            ul.asset,
            a.asset_name,
            a.asset_category,
            SUM(COALESCE(ul.planned_hours, 0)) AS planned_hours,
            SUM(COALESCE(ul.actual_hours, 0)) AS actual_hours,
            SUM(COALESCE(ul.idle_hours, 0)) AS idle_hours
        FROM `tabAsset Utilization Log` ul
        JOIN `tabAsset` a ON a.name = ul.asset
        {conditions}
        GROUP BY ul.asset
    """, params, as_dict=True)

    # Get downtime from Asset Repair
    repair_conditions = "WHERE r.docstatus = 1"
    if filters.get("from_date"):
        repair_conditions += " AND r.failure_date >= %(from_date)s"
    if filters.get("to_date"):
        repair_conditions += " AND r.failure_date <= %(to_date)s"

    downtime_map = {}
    repair_data = frappe.db.sql(f"""
        SELECT asset, SUM(COALESCE(downtime, 0)) AS downtime_hours
        FROM `tabAsset Repair`
        {repair_conditions}
        GROUP BY asset
    """, params, as_dict=True)
    for r in repair_data:
        downtime_map[r["asset"]] = flt(r["downtime_hours"])

    result = []
    for row in util_data:
        planned = flt(row.planned_hours)
        actual  = flt(row.actual_hours)
        downtime = downtime_map.get(row.asset, 0)
        idle = flt(row.idle_hours)

        if planned <= 0:
            continue

        # Availability = (planned - downtime) / planned
        availability = flt(max(planned - downtime, 0) / planned * 100, 1)

        # Performance = actual / (planned - downtime)  — how much of available time was used
        available_time = max(planned - downtime, 0.001)
        performance = flt(min(actual / available_time * 100, 100), 1)

        # Quality — derived from idle ratio (proxy when no defect data available)
        # idle_hours = time running but producing nothing (setup, adjustment, etc.)
        quality = flt(max((actual - idle) / max(actual, 0.001) * 100, 0), 1) if actual > 0 else 100

        oee = flt(availability * performance * quality / 10000, 1)

        if oee >= 85:
            oee_class = "عالمي ≥85%"
        elif oee >= 65:
            oee_class = "جيد ≥65%"
        elif oee >= 40:
            oee_class = "متوسط ≥40%"
        else:
            oee_class = "منخفض <40%"

        result.append({
            "asset": row.asset,
            "asset_name": row.asset_name,
            "asset_category": row.asset_category,
            "planned_hours": planned,
            "actual_hours": actual,
            "downtime_hours": downtime,
            "availability_pct": availability,
            "performance_pct": performance,
            "quality_pct": quality,
            "oee_pct": oee,
            "oee_class": oee_class,
        })

    return sorted(result, key=lambda x: x["oee_pct"])


def get_chart(data):
    if not data:
        return None
    top = data[:12]
    return {
        "data": {
            "labels": [d["asset_name"][:20] for d in top],
            "datasets": [
                {"name": "التوافر %", "values": [d["availability_pct"] for d in top]},
                {"name": "الأداء %", "values": [d["performance_pct"] for d in top]},
                {"name": "OEE %", "values": [d["oee_pct"] for d in top]},
            ],
        },
        "type": "bar",
        "colors": ["#10B981", "#3B82F6", "#D97706"],
        "title": "OEE — فعالية المعدات الشاملة",
    }


def get_summary(data):
    if not data:
        return []
    avg_oee = flt(sum(d["oee_pct"] for d in data) / max(len(data), 1), 1)
    avg_avail = flt(sum(d["availability_pct"] for d in data) / max(len(data), 1), 1)
    world_class = sum(1 for d in data if d["oee_pct"] >= 85)
    critical = sum(1 for d in data if d["oee_pct"] < 40)
    return [
        {"label": _("متوسط OEE"), "value": f"{avg_oee}%",
         "indicator": "Green" if avg_oee >= 65 else "Orange"},
        {"label": _("متوسط التوافر"), "value": f"{avg_avail}%",
         "indicator": "Green" if avg_avail >= 90 else "Orange"},
        {"label": _("أصول ذات أداء عالمي ≥85%"), "value": world_class, "indicator": "Green"},
        {"label": _("أصول حرجة <40%"), "value": critical,
         "indicator": "Red" if critical > 0 else "Green"},
    ]
