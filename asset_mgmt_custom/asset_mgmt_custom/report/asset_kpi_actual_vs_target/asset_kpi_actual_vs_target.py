"""
Asset KPI Actual vs Target
---------------------------
Asset KPI Target كان DocType بيانات مستهدَفة (لكل فئة أصل + سنة مالية:
استخدام%، توقف شهري، تكلفة صيانة شهرية، MTBF/MTTR، حوادث شهرية) بلا
أي مقارنة فعلية في أي مكان بالتطبيق — أرقام تُدخَل ولا تُقرأ أبداً.

هذا التقرير يحسب القيم الفعلية من نفس مصادر البيانات المستخدمة أصلاً في
تقارير أخرى لهذا التطبيق، بلا تكرار منطق:
  - MTBF/MTTR: نفس صيغة asset_mtbf_mttr_analysis بالضبط (period_days /
    failure_count، ومتوسط Asset Repair.downtime) لكن مجمَّعة على مستوى
    الفئة كلها خلال السنة المالية بأكملها (عيّنة أكبر لدلالة إحصائية،
    خلافاً للمقاييس الشهرية أدناه).
  - الاستخدام%/التوقف الشهري: من Asset Utilization Log خلال الشهر
    المحدَّد فقط.
  - تكلفة الصيانة الشهرية: من Asset Repair.repair_cost خلال نفس الشهر.
  - الحوادث الشهرية: من Asset Incident Report خلال نفس الشهر.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, date_diff, flt, get_first_day, get_last_day, getdate, nowdate


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("الفئة"), "fieldname": "asset_category", "fieldtype": "Link", "options": "Asset Category", "width": 140},
        {"label": _("السنة المالية"), "fieldname": "fiscal_year", "fieldtype": "Link", "options": "Fiscal Year", "width": 100},
        {"label": _("الاستخدام% (فعلي/هدف)"), "fieldname": "utilization_display", "fieldtype": "Data", "width": 150},
        {"label": _("توقف شهري (فعلي/هدف)"), "fieldname": "downtime_display", "fieldtype": "Data", "width": 160},
        {"label": _("تكلفة صيانة شهرية (فعلي/هدف)"), "fieldname": "cost_display", "fieldtype": "Data", "width": 200},
        {"label": _("MTBF أيام (فعلي/هدف)"), "fieldname": "mtbf_display", "fieldtype": "Data", "width": 150},
        {"label": _("MTTR ساعة (فعلي/هدف)"), "fieldname": "mttr_display", "fieldtype": "Data", "width": 150},
        {"label": _("حوادث شهرية (فعلي/هدف)"), "fieldname": "incidents_display", "fieldtype": "Data", "width": 150},
        {"label": _("الحالة العامة"), "fieldname": "status", "fieldtype": "Data", "width": 130},
    ]


def _fmt_pair(actual, target, unit="", precision=1):
    actual_str = "—" if actual is None else f"{round(actual, precision)}{unit}"
    target_str = f"{target}{unit}" if target else "—"
    return f"{actual_str} / {target_str}"


def _resolve_month_start(fy_dates, month):
    for candidate_year in (getdate(fy_dates.year_start_date).year, getdate(fy_dates.year_end_date).year):
        candidate = getdate(f"{candidate_year}-{month:02d}-01")
        if fy_dates.year_start_date <= candidate <= fy_dates.year_end_date:
            return candidate
    return get_first_day(fy_dates.year_start_date)


def get_data(filters):
    fy = filters.get("fiscal_year")
    fy_dates = frappe.db.get_value("Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True)
    if not fy_dates:
        return []

    target_filters = {"fiscal_year": fy}
    if filters.get("asset_category"):
        target_filters["asset_category"] = filters["asset_category"]

    targets = frappe.get_all(
        "Asset KPI Target",
        filters=target_filters,
        fields=[
            "asset_category", "fiscal_year", "target_utilization_pct",
            "max_downtime_hours_monthly", "max_maintenance_cost_monthly",
            "target_mtbf_days", "target_mttr_hours", "max_incidents_monthly",
        ],
    )
    if not targets:
        return []

    month = cint(filters.get("month")) or getdate(nowdate()).month
    month_start = _resolve_month_start(fy_dates, month)
    month_end = get_last_day(month_start)
    next_month_start = add_months(month_start, 1)

    rows = []
    for t in targets:
        category = t.asset_category

        repair_stats = frappe.db.sql("""
            SELECT COUNT(r.name) AS failure_count, SUM(COALESCE(r.downtime, 0)) AS total_downtime
            FROM `tabAsset Repair` r
            JOIN `tabAsset` a ON a.name = r.asset
            WHERE a.asset_category = %(category)s AND r.docstatus = 1
              AND r.failure_date BETWEEN %(from_date)s AND %(to_date)s
        """, {"category": category, "from_date": fy_dates.year_start_date, "to_date": fy_dates.year_end_date}, as_dict=True)[0]

        failure_count = cint(repair_stats.failure_count)
        period_days = max(date_diff(fy_dates.year_end_date, fy_dates.year_start_date), 1)
        actual_mtbf = flt(period_days / failure_count, 1) if failure_count else None
        actual_mttr = flt(flt(repair_stats.total_downtime) / failure_count, 1) if failure_count else None

        util = frappe.db.sql("""
            SELECT AVG(u.utilization_pct) AS avg_util, SUM(u.downtime_hours) AS total_downtime_month
            FROM `tabAsset Utilization Log` u
            JOIN `tabAsset` a ON a.name = u.asset
            WHERE a.asset_category = %(category)s
              AND u.log_date BETWEEN %(from_date)s AND %(to_date)s
        """, {"category": category, "from_date": month_start, "to_date": month_end}, as_dict=True)[0]

        cost_row = frappe.db.sql("""
            SELECT SUM(COALESCE(r.repair_cost, 0)) AS total_cost
            FROM `tabAsset Repair` r
            JOIN `tabAsset` a ON a.name = r.asset
            WHERE a.asset_category = %(category)s AND r.docstatus = 1
              AND r.failure_date BETWEEN %(from_date)s AND %(to_date)s
        """, {"category": category, "from_date": month_start, "to_date": month_end}, as_dict=True)[0]

        incident_count = frappe.db.sql("""
            SELECT COUNT(i.name)
            FROM `tabAsset Incident Report` i
            JOIN `tabAsset` a ON a.name = i.asset
            WHERE a.asset_category = %(category)s
              AND i.incident_date >= %(from_date)s AND i.incident_date < %(to_date)s
        """, {"category": category, "from_date": month_start, "to_date": next_month_start})[0][0] or 0

        breaches = []
        avg_util = util.avg_util
        if t.target_utilization_pct and avg_util is not None and flt(avg_util) < flt(t.target_utilization_pct):
            breaches.append("utilization")
        if t.max_downtime_hours_monthly and flt(util.total_downtime_month) > flt(t.max_downtime_hours_monthly):
            breaches.append("downtime")
        if t.max_maintenance_cost_monthly and flt(cost_row.total_cost) > flt(t.max_maintenance_cost_monthly):
            breaches.append("cost")
        if t.target_mtbf_days and actual_mtbf is not None and actual_mtbf < flt(t.target_mtbf_days):
            breaches.append("mtbf")
        if t.target_mttr_hours and actual_mttr is not None and actual_mttr > flt(t.target_mttr_hours):
            breaches.append("mttr")
        if t.max_incidents_monthly is not None and incident_count > cint(t.max_incidents_monthly):
            breaches.append("incidents")

        rows.append({
            "asset_category": category,
            "fiscal_year": t.fiscal_year,
            "utilization_display": _fmt_pair(avg_util, t.target_utilization_pct, "%"),
            "downtime_display": _fmt_pair(flt(util.total_downtime_month), t.max_downtime_hours_monthly, "h"),
            "cost_display": _fmt_pair(flt(cost_row.total_cost), t.max_maintenance_cost_monthly),
            "mtbf_display": _fmt_pair(actual_mtbf, t.target_mtbf_days),
            "mttr_display": _fmt_pair(actual_mttr, t.target_mttr_hours),
            "incidents_display": _fmt_pair(incident_count, t.max_incidents_monthly, precision=0),
            "status": _("⚠️ {0} مؤشر متجاوز").format(len(breaches)) if breaches else _("✅ ضمن الهدف"),
        })

    return rows
