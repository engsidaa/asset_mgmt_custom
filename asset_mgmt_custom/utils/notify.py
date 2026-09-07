import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification


def notify_user(user, subject, reference_doctype=None, reference_name=None):
    """
    غلاف رفيع حول آلية Notification Log الأصلية في Frappe (نفس الجدول الذي
    يُغذّي جرس التنبيهات في واجهة Desk القياسية) — بدل اختراع جدول/مصدر
    بيانات موازٍ، فتطبيق الموبايل يقرأ نفس السجلّات الحقيقية المرتبطة
    بحساب المستخدم على الخادم (for_user)، وتُصبح "مقروءة" بنفس حقل read
    القياسي عند فتحها. type="Alert" عمداً: هو النوع الوحيد الذي يُنشئ
    السجل حتى لو from_user == for_user (حالتنا الشائعة: نظام يُشعِر
    مستخدماً بعينه)، وأيضاً يتجاوز فحص إعدادات إشعارات البريد الإلكتروني
    الخاصة بالأنواع الأخرى (Mention/Assignment...) التي لا تنطبق هنا.
    """
    if not user:
        return
    enqueue_create_notification(user, {
        "type": "Alert",
        "subject": subject,
        "document_type": reference_doctype,
        "document_name": reference_name,
        "from_user": frappe.session.user,
    })
