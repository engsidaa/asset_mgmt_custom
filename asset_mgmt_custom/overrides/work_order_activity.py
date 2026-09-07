"""
تنبيهات نشاط أمر العمل — تعليق جديد أو ملف مُرفَق. كلاهما يمر عبر مسارات
Frappe العامة (frappe.desk.form.utils.add_comment، ورفع ملف عام
doctype=Asset Work Order) وليس عبر دالة مخصصة في هذا التطبيق يمكن ربط
الإشعار بها مباشرة — لذلك يُلتقَط الحدث هنا عبر doc_events على Comment/
File أنفسهما (مُسجَّلة في hooks.py)، ومُصفَّى صراحة لِـ reference_doctype/
attached_to_doctype == "Asset Work Order" فقط حتى لا يُشعِر أي تعليق أو
ملف آخر بالنظام بالخطأ.
"""

import frappe
from frappe import _

from asset_mgmt_custom.utils.notify import notify_user


def _notify_other_party(work_order_name, actor_user, action_text):
    wo = frappe.db.get_value(
        "Asset Work Order", work_order_name, ["title", "requested_by", "assigned_technician"], as_dict=True
    )
    if not wo:
        return

    requester_user = wo.requested_by
    technician_user = wo.assigned_technician

    recipients = {requester_user, technician_user} - {actor_user, None, ""}
    for user in recipients:
        notify_user(
            user,
            _("{0} في أمر العمل {1}.").format(action_text, wo.title),
            reference_doctype="Asset Work Order",
            reference_name=work_order_name,
        )


def notify_on_comment(doc, method=None):
    if doc.reference_doctype != "Asset Work Order" or doc.comment_type != "Comment":
        return
    _notify_other_party(doc.reference_name, doc.owner, _("تم إضافة تعليق جديد"))


def notify_on_file_attach(doc, method=None):
    if doc.attached_to_doctype != "Asset Work Order" or not doc.attached_to_name:
        return
    _notify_other_party(doc.attached_to_name, doc.owner, _("تم إرفاق ملف جديد"))
