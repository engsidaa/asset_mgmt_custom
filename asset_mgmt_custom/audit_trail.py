"""
سجل التدقيق الكامل للأصل (Full Audit Trail)
----------------------------------------------
تجميع سجل تاريخي واحد مرتب زمنياً من كل السجلات المرتبطة بأصل معيّن عبر
عدة DocTypes (نشاط، تعليقات، أوامر عمل، إصلاحات، فحوصات سلامة، تحليلات
أعطال، مطالبات ضمان، شهادات امتثال) — بدل تصفح كل مستند على حدة يدوياً
بحثاً عن تاريخ أصل كامل (تدقيق داخلي/خارجي، تحقيق حادثة، تقييم قبل بيع).

يُستدعى من Print Format "Asset Full Audit Trail" مباشرة عبر
`frappe.call(...)` داخل قالب Jinja (متاحة ضمن بيئة Jinja الآمنة نفسها
المستخدمة في كل قوالب الطباعة بهذا التطبيق) — نقطة تجميع واحدة، لا تكرار
منطق الاستعلام في القالب نفسه.
"""

import frappe
from frappe import _
from frappe.utils import cstr


@frappe.whitelist()
def get_asset_audit_trail(asset):
    if not frappe.db.exists("Asset", asset):
        frappe.throw(_("Asset {0} not found.").format(asset))

    entries = []
    entries += _activity_entries(asset)
    entries += _comment_entries(asset)
    entries += _work_order_entries(asset)
    entries += _repair_entries(asset)
    entries += _inspection_entries(asset)
    entries += _failure_analysis_entries(asset)
    entries += _warranty_claim_entries(asset)
    entries += _compliance_certificate_entries(asset)

    entries.sort(key=lambda e: cstr(e["date"]), reverse=True)
    return entries


def _entry(date, type_label, summary, reference_doctype, reference_name):
    return {
        "date": date,
        "type_label": type_label,
        "summary": summary,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
    }


def _activity_entries(asset):
    rows = frappe.get_all(
        "Asset Activity",
        filters={"asset": asset},
        fields=["name", "date", "subject"],
    )
    return [_entry(r.date, _("نشاط"), r.subject, "Asset Activity", r.name) for r in rows]


def _comment_entries(asset):
    rows = frappe.get_all(
        "Comment",
        filters={"reference_doctype": "Asset", "reference_name": asset, "comment_type": "Comment"},
        fields=["name", "creation", "content", "comment_by"],
    )
    return [
        _entry(r.creation, _("تعليق"), f"{r.comment_by}: {frappe.utils.strip_html(r.content or '')}", "Comment", r.name)
        for r in rows
    ]


def _work_order_entries(asset):
    rows = frappe.get_all(
        "Asset Work Order",
        filters={"asset": asset, "docstatus": ["!=", 2]},
        fields=["name", "request_date", "status", "priority", "problem_description"],
    )
    return [
        _entry(
            r.request_date,
            _("أمر عمل"),
            _("{0} — الأولوية: {1} — {2}").format(r.status, r.priority, r.problem_description or ""),
            "Asset Work Order",
            r.name,
        )
        for r in rows
    ]


def _repair_entries(asset):
    rows = frappe.get_all(
        "Asset Repair",
        filters={"asset": asset, "docstatus": ["!=", 2]},
        fields=["name", "failure_date", "repair_status", "repair_cost", "description"],
    )
    return [
        _entry(
            r.failure_date,
            _("إصلاح"),
            _("{0} — التكلفة: {1} — {2}").format(r.repair_status, r.repair_cost or 0, r.description or ""),
            "Asset Repair",
            r.name,
        )
        for r in rows
    ]


def _inspection_entries(asset):
    rows = frappe.get_all(
        "Asset Safety Inspection",
        filters={"asset": asset, "docstatus": ["!=", 2]},
        fields=["name", "inspection_date", "inspection_type", "overall_result"],
    )
    return [
        _entry(
            r.inspection_date,
            _("فحص سلامة"),
            _("{0} — النتيجة: {1}").format(r.inspection_type, r.overall_result),
            "Asset Safety Inspection",
            r.name,
        )
        for r in rows
    ]


def _failure_analysis_entries(asset):
    rows = frappe.get_all(
        "Asset Failure Analysis",
        filters={"asset": asset},
        fields=["name", "failure_date", "failure_mode", "root_cause"],
    )
    return [
        _entry(
            r.failure_date,
            _("تحليل عطل"),
            _("السبب الجذري: {0} — {1}").format(r.failure_mode or "-", r.root_cause or ""),
            "Asset Failure Analysis",
            r.name,
        )
        for r in rows
    ]


def _warranty_claim_entries(asset):
    rows = frappe.get_all(
        "Asset Warranty Claim",
        filters={"asset": asset, "docstatus": ["!=", 2]},
        fields=["name", "claim_date", "status", "issue_description"],
    )
    return [
        _entry(
            r.claim_date,
            _("مطالبة ضمان"),
            _("{0} — {1}").format(r.status, frappe.utils.strip_html(r.issue_description or "")),
            "Asset Warranty Claim",
            r.name,
        )
        for r in rows
    ]


def _compliance_certificate_entries(asset):
    rows = frappe.get_all(
        "Asset Compliance Certificate",
        filters={"asset": asset},
        fields=["name", "issue_date", "certificate_type", "status", "expiry_date"],
    )
    return [
        _entry(
            r.issue_date,
            _("شهادة امتثال"),
            _("{0} — الحالة: {1} — تنتهي في: {2}").format(r.certificate_type, r.status, r.expiry_date or "-"),
            "Asset Compliance Certificate",
            r.name,
        )
        for r in rows
    ]
