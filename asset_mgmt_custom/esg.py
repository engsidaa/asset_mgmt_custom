"""
محاسبة الكربون (ESG) وكشف شذوذ استهلاك الطاقة
------------------------------------------------
منطق مشترك بين Asset Energy Log وAsset Fuel Log — بدل تكرار حساب
مكافئ الكربون وفحص الشذوذ في كل controller على حدة.
"""

import frappe
from frappe import _
from frappe.utils import flt, today


def get_settings():
    return frappe.get_cached_doc("Asset Mgmt Settings")


def get_electricity_emission_factor():
    return flt(get_settings().electricity_emission_factor)


def get_fuel_emission_factor(fuel_type):
    settings = get_settings()
    return {
        "Diesel": flt(settings.diesel_emission_factor),
        "Petrol": flt(settings.petrol_emission_factor),
        "Natural Gas": flt(settings.natural_gas_emission_factor),
    }.get(fuel_type, 0)


def check_anomaly(doctype, asset, current_value, exclude_name, value_fieldname):
    """
    يقارن current_value (وحدات كهرباء مستهلكة، أو لترات وقود) بمتوسط آخر
    6 سجلات سابقة فعلية لنفس الأصل تحديداً (وليس معياراً على مستوى
    الأسطول بالكامل — "معدلها القياسي" الخاص بها) — يتطلب 3 سجلات سابقة
    على الأقل لعيّنة ذات دلالة، وإلا لا يُطلَق أي حكم على بيانات غير كافية.
    """
    if not asset or not current_value:
        return False, None

    history = frappe.get_all(
        doctype,
        filters={"asset": asset, "name": ["!=", exclude_name]},
        fields=[value_fieldname],
        order_by="creation desc",
        limit_page_length=6,
    )
    values = [flt(r.get(value_fieldname)) for r in history if flt(r.get(value_fieldname)) > 0]
    if len(values) < 3:
        return False, None

    baseline = sum(values) / len(values)
    if not baseline:
        return False, baseline

    threshold_pct = flt(get_settings().energy_anomaly_threshold_pct) or 15
    deviation_pct = ((flt(current_value) - baseline) / baseline) * 100
    return deviation_pct > threshold_pct, baseline


def create_early_inspection_alert(source_doctype, source_name, asset, current_value, baseline, unit_label):
    """أمر عمل 'فحص' بأولوية 'عاجل' — مؤشر مبكر يستحق فحصاً فنياً قريباً،
    وليس عطلاً مؤكداً (لذلك ليس 'حرج')."""
    branch = frappe.db.get_value("Asset", asset, "custom_branch")
    asset_name = frappe.db.get_value("Asset", asset, "asset_name") or asset

    wo = frappe.new_doc("Asset Work Order")
    wo.asset = asset
    wo.branch = branch
    wo.work_type = "فحص"
    wo.priority = "عاجل"
    wo.request_date = today()
    wo.problem_description = _(
        "Auto-generated: energy/fuel consumption anomaly detected on {0} — current {1} {2} vs. "
        "this asset's own historical average {3} {2} (source: {4} {5})."
    ).format(asset_name, current_value, unit_label, round(baseline, 2), source_doctype, source_name)

    try:
        wo.insert(ignore_permissions=True)
        return wo.name
    except Exception:
        frappe.log_error(title="Auto energy-anomaly inspection Work Order failed", message=frappe.get_traceback())
        return None
