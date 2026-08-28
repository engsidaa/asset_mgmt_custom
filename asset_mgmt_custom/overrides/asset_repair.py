"""
Asset Repair override
---------------------
Validate:
  - عند اكتمال الإصلاح (Completed): يُشترط اسم الفني + ملاحظات الإصلاح + تاريخ الاكتمال
  - CapEx/OpEx: إذا كان إصلاح ضمان، تُصفَّر التكاليف
  - CapEx/OpEx: إذا تجاوزت التكلفة حد الرسملة في Asset Category، يُفعَّل capitalize_repair_cost
  - CapEx: عند اكتمال إصلاح مُرسمَل (capitalize_repair_cost)، يُشترط إدخال عدد الشهور
    الإضافية للعمر الإنتاجي (increase_in_asset_life) — بدونها ERPNext يرسمل التكلفة
    لكن لا يمدد العمر ولا يعيد جدولة الإهلاك

On Submit:
  - يُحدِّث إجمالي تكلفة الصيانة (custom_total_maintenance_cost) على الأصل
  - يُحدِّث تاريخ آخر صيانة (custom_last_maintenance_date) على الأصل
  - يُسجِّل ملخص الإصلاح في Asset Activity

On Cancel:
  - يُعيد حساب إجمالي التكلفة وتاريخ آخر صيانة بعد حذف هذا السند
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, time_diff_in_hours


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate(doc, method=None):
    if doc.repair_status == "Completed":
        _validate_completion_requirements(doc)
    _auto_classify_capex(doc)
    _calculate_downtime(doc)
    if doc.repair_status == "Completed":
        _require_life_extension_when_capitalized(doc)


def _calculate_downtime(doc):
    if doc.get("custom_downtime_start") and doc.get("custom_downtime_end"):
        hours = time_diff_in_hours(doc.custom_downtime_end, doc.custom_downtime_start)
        doc.custom_downtime_hours = round(max(hours, 0), 2)
    else:
        doc.custom_downtime_hours = 0


def _validate_completion_requirements(doc):
    """تحقق من اكتمال بيانات التوثيق قبل إغلاق طلب الإصلاح."""
    errors = []

    if not doc.get("custom_technician_name"):
        errors.append(_("Technician Name is required when marking repair as Completed."))

    if not doc.get("custom_repair_notes"):
        errors.append(_("Repair Notes (detailed description) is required when marking repair as Completed."))

    if not doc.completion_date:
        errors.append(_("Completion Date is required when marking repair as Completed."))

    if errors:
        frappe.throw(
            "<br>".join(errors),
            title=_("Repair Documentation Incomplete"),
        )


def _auto_classify_capex(doc):
    """If warranty repair, zero out costs. If cost > threshold, auto-set capitalize."""
    if doc.get("custom_is_warranty_repair"):
        doc.capitalize_repair_cost = 0
        return

    if not doc.asset_category:
        doc.asset_category = frappe.db.get_value("Asset", doc.asset, "asset_category")

    threshold = 0
    if doc.asset_category:
        threshold = frappe.db.get_value(
            "Asset Category", doc.asset_category, "custom_capitalization_threshold"
        ) or 0

    total = flt(doc.repair_cost) + flt(doc.get("custom_labor_cost"))
    if threshold and total > flt(threshold):
        doc.capitalize_repair_cost = 1


def _require_life_extension_when_capitalized(doc):
    """
    ERPNext رسملة (capitalize_repair_cost) بدون increase_in_asset_life تُضيف
    التكلفة لقيمة الأصل لكن لا تمدد العمر الإنتاجي ولا تعيد جدولة الإهلاك —
    وده غالباً غلط محاسبي غير مقصود. نجبر إدخال القيمة قبل اكتمال أي إصلاح مُرسمَل.
    """
    if not doc.get("capitalize_repair_cost"):
        return
    if not doc.get("increase_in_asset_life"):
        frappe.throw(
            _(
                "Please enter 'Increase In Asset Life (Months)' before completing a "
                "capitalized (CapEx) repair — otherwise the cost is capitalized but the "
                "asset's useful life and depreciation schedule are never extended."
            ),
            title=_("Missing Life Extension"),
        )


# ---------------------------------------------------------------------------
# On Submit
# ---------------------------------------------------------------------------

def on_submit(doc, method=None):
    _update_asset_maintenance_summary(doc.asset)
    _log_repair_activity(doc)


def _update_asset_maintenance_summary(asset_name):
    """
    يُعيد حساب:
    - إجمالي تكلفة جميع الإصلاحات المُقدَّمة على الأصل
    - تاريخ آخر إصلاح مكتمل
    """
    totals = frappe.db.sql(
        """
        SELECT
            SUM(total_repair_cost + IFNULL(custom_labor_cost, 0)) AS total_cost,
            MAX(CASE WHEN repair_status = 'Completed' THEN DATE(completion_date) END) AS last_date,
            SUM(IFNULL(custom_downtime_hours, 0)) AS total_downtime
        FROM `tabAsset Repair`
        WHERE asset = %s AND docstatus = 1
        """,
        asset_name,
        as_dict=True,
    )

    total_cost = flt(totals[0].total_cost) if totals else 0.0
    last_date = totals[0].last_date if totals else None
    total_downtime = flt(totals[0].total_downtime) if totals else 0.0

    frappe.db.set_value(
        "Asset",
        asset_name,
        {
            "custom_total_maintenance_cost": total_cost,
            "custom_last_maintenance_date": last_date,
            "custom_total_downtime_hours": total_downtime,
        },
        update_modified=False,
    )


def _log_repair_activity(doc):
    """تسجيل ملخص الإصلاح في سجل نشاط الأصل."""
    labor = flt(doc.get("custom_labor_cost"))
    total = flt(doc.total_repair_cost) + labor
    technician = doc.get("custom_technician_name") or _("Unknown")

    subject = _(
        "Asset Repair {0} submitted – Status: {1} | Technician: {2} | Total Cost: {3}"
    ).format(doc.name, doc.repair_status, technician, total)

    frappe.get_doc(
        {
            "doctype": "Asset Activity",
            "asset": doc.asset,
            "subject": subject,
            "user": frappe.session.user,
            "date": now_datetime(),
        }
    ).insert(ignore_permissions=True, ignore_links=True)


# ---------------------------------------------------------------------------
# On Cancel
# ---------------------------------------------------------------------------

def on_cancel(doc, method=None):
    _update_asset_maintenance_summary(doc.asset)

    frappe.get_doc(
        {
            "doctype": "Asset Activity",
            "asset": doc.asset,
            "subject": _("Asset Repair {0} cancelled – maintenance totals recalculated.").format(doc.name),
            "user": frappe.session.user,
            "date": now_datetime(),
        }
    ).insert(ignore_permissions=True, ignore_links=True)
