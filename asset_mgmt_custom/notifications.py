"""
تنبيهات فورية للأعطال الحرجة (واتساب/SMS)
-------------------------------------------
هذا التطبيق لا يرسل واتساب/SMS مباشرة (يحتاج بيانات اعتماد بوابة فعلية
لا تتوفر هنا) — بدلاً من ذلك، يُسلِّم حمولة JSON عبر HTTP POST لأي رابط
Webhook يحدده المستخدم في Asset Mgmt Settings (بوابة Twilio مباشرة، أو
أتمتة عبر Zapier/Make/n8n تتولى الإرسال الفعلي). هذا يجعل الميزة تعمل مع
أي بوابة اختارها المستخدم بدل افتراض مزوّد بعينه.
"""

import frappe


def send_critical_alert(subject, message, reference_doctype=None, reference_name=None):
    settings = frappe.get_single("Asset Mgmt Settings")
    if not settings.get("critical_alerts_enabled"):
        return
    if not settings.get("critical_alert_webhook_url"):
        return

    recipients = [
        r.strip() for r in (settings.get("critical_alert_recipients") or "").split(",") if r.strip()
    ]
    if not recipients:
        return

    payload = {
        "subject": subject,
        "message": message,
        "recipients": recipients,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
    }

    try:
        import requests

        requests.post(settings.critical_alert_webhook_url, json=payload, timeout=10)
    except Exception:
        frappe.log_error(title="send_critical_alert failed", message=frappe.get_traceback())
