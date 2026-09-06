"""
مؤشر صحة الفرع (Branch Health Score)
------------------------------------
رقم واحد مركَّب لكل فرع (0-100، كلما زاد كان أفضل) يجمع أربعة مؤشرات
سلبية موجودة بالفعل في التطبيق (ساعات التوقف، خرق SLA، تكرار الأعطال
عبر أوامر العمل المفتوحة، ونسبة تكلفة الصيانة للقيمة الدفترية)، بدل ما
تُقرَأ منفصلة في تقارير متعددة.

هذه صيغة ترجيح مبدئية شفّافة (موضَّحة أدناه بالكامل، وليست معادلة
مغلقة) — قابلة للتعديل لاحقاً حسب خبرة تشغيلية فعلية:

  health_score = 100
    − min(نسبة تكلفة الصيانة٪, 40)                         (سقف 40 نقطة)
    − min(عدد أوامر عمل خارقة لـ SLA × 5, 30)               (سقف 30 نقطة)
    − min(إجمالي ساعات التوقف ÷ 10, 20)                      (سقف 20 نقطة)
    − min(عدد أوامر العمل المفتوحة حالياً × 2, 10)           (سقف 10 نقاط)
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("الفرع"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 150},
        {"label": _("عدد الأصول"), "fieldname": "asset_count", "fieldtype": "Int", "width": 90},
        {"label": _("ساعات التوقف"), "fieldname": "total_downtime_hours", "fieldtype": "Float", "width": 110},
        {"label": _("تكلفة الصيانة"), "fieldname": "total_maintenance_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("نسبة التكلفة / القيمة %"), "fieldname": "cost_ratio_pct", "fieldtype": "Percent", "width": 150},
        {"label": _("أوامر عمل مفتوحة"), "fieldname": "open_wo_count", "fieldtype": "Int", "width": 120},
        {"label": _("خرق SLA"), "fieldname": "sla_breach_count", "fieldtype": "Int", "width": 90},
        {"label": _("مؤشر الصحة"), "fieldname": "health_score", "fieldtype": "Float", "width": 100},
        {"label": _("الحالة"), "fieldname": "status_label", "fieldtype": "Data", "width": 130},
    ]


def get_data(filters):
    asset_condition = ""
    values = {}
    if filters.get("company"):
        asset_condition = " AND a.company = %(company)s"
        values["company"] = filters["company"]

    branch_stats = frappe.db.sql(
        f"""
        SELECT
            br.name AS branch,
            COUNT(DISTINCT a.name) AS asset_count,
            IFNULL(SUM(a.custom_total_downtime_hours), 0) AS total_downtime_hours,
            IFNULL(SUM(a.custom_total_maintenance_cost), 0) AS total_maintenance_cost,
            IFNULL(SUM(IFNULL(a.value_after_depreciation, a.gross_purchase_amount)), 0) AS total_asset_value
        FROM `tabBranch` br
        LEFT JOIN `tabAsset` a ON a.custom_branch = br.name AND a.docstatus < 2 {asset_condition}
        GROUP BY br.name
        HAVING asset_count > 0
        """,
        values,
        as_dict=True,
    )

    wo_stats = {
        row.branch: row
        for row in frappe.db.sql(
            """
            SELECT
                branch,
                SUM(CASE WHEN status IN ('مفتوح', 'قيد التنفيذ', 'معلق') THEN 1 ELSE 0 END) AS open_wo_count,
                SUM(IFNULL(sla_breached, 0)) AS sla_breach_count
            FROM `tabAsset Work Order`
            WHERE docstatus = 1 AND branch IS NOT NULL AND branch != ''
            GROUP BY branch
            """,
            as_dict=True,
        )
        if row.branch
    }

    data = []
    for row in branch_stats:
        wo = wo_stats.get(row.branch, frappe._dict(open_wo_count=0, sla_breach_count=0))
        row.open_wo_count = int(wo.open_wo_count or 0)
        row.sla_breach_count = int(wo.sla_breach_count or 0)

        row.cost_ratio_pct = (
            round(flt(row.total_maintenance_cost) * 100 / flt(row.total_asset_value), 1)
            if flt(row.total_asset_value) > 0 else 0
        )

        deduction = (
            min(row.cost_ratio_pct, 40)
            + min(row.sla_breach_count * 5, 30)
            + min(flt(row.total_downtime_hours) / 10, 20)
            + min(row.open_wo_count * 2, 10)
        )
        row.health_score = round(max(100 - deduction, 0), 1)

        if row.health_score >= 85:
            row.status_label = _("✅ ممتاز")
        elif row.health_score >= 65:
            row.status_label = _("🟢 جيد")
        elif row.health_score >= 40:
            row.status_label = _("🟡 يحتاج متابعة")
        else:
            row.status_label = _("🔴 حرج")

        data.append(row)

    return sorted(data, key=lambda r: r.health_score)
