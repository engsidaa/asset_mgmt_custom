"""
تنبيهات فورية للأعطال الحرجة (واتساب/SMS)
-------------------------------------------
مسارين مستقلين تماماً، يمكن تفعيل أحدهما أو كليهما معاً:

1. Webhook عام (كما كان): يُسلِّم حمولة JSON لأي رابط يحدده المستخدم
   (بوابة Twilio الخاصة به، أو أتمتة عبر Zapier/Make/n8n) — يناسب من
   يملك بالفعل تكاملاً جاهزاً أو يفضّل مزوّداً آخر غير Twilio.
2. إرسال مباشر عبر Twilio REST API (جديد): عند تفعيله في Asset Mgmt
   Settings مع Account SID/Auth Token فعليين، تُرسَل رسالة SMS/واتساب
   حقيقية لكل رقم في نفس قائمة "أرقام المستلمين" — بدون أي مكتبة SDK
   خارجية (Twilio Messages API REST بسيط: POST + HTTP Basic Auth، بنفس
   أسلوب `requests` المُستخدَم أصلاً في مسار الـ Webhook).

كلا المسارين يقرآن نفس settings.critical_alert_recipients — لا تكرار
لحقل قائمة المستلمين.
"""

import frappe


def send_critical_alert(subject, message, reference_doctype=None, reference_name=None):
    settings = frappe.get_single("Asset Mgmt Settings")
    if not settings.get("critical_alerts_enabled"):
        return

    recipients = [
        r.strip() for r in (settings.get("critical_alert_recipients") or "").split(",") if r.strip()
    ]
    if not recipients:
        return

    if settings.get("critical_alert_webhook_url"):
        _send_via_webhook(settings, subject, message, recipients, reference_doctype, reference_name)

    if settings.get("twilio_enabled"):
        _send_via_twilio(settings, subject, message, recipients)


def _send_via_webhook(settings, subject, message, recipients, reference_doctype, reference_name):
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
        frappe.log_error(title="send_critical_alert (webhook) failed", message=frappe.get_traceback())


def _send_via_twilio(settings, subject, message, recipients):
    account_sid = settings.get("twilio_account_sid")
    auth_token = settings.get_password("twilio_auth_token", raise_exception=False)
    if not account_sid or not auth_token:
        return

    channel = settings.get("twilio_channel") or "WhatsApp"
    from_numbers = []
    if channel in ("SMS", "كلاهما") and settings.get("twilio_from_number"):
        from_numbers.append((settings.twilio_from_number, False))
    if channel in ("WhatsApp", "كلاهما") and settings.get("twilio_whatsapp_from_number"):
        from_numbers.append((settings.twilio_whatsapp_from_number, True))
    if not from_numbers:
        return

    body = f"{subject}\n{message}"
    api_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    import requests

    for recipient in recipients:
        for from_number, is_whatsapp in from_numbers:
            try:
                requests.post(
                    api_url,
                    auth=(account_sid, auth_token),
                    data={
                        "From": _twilio_number(from_number, is_whatsapp),
                        "To": _twilio_number(recipient, is_whatsapp),
                        "Body": body,
                    },
                    timeout=10,
                )
            except Exception:
                frappe.log_error(title="send_critical_alert (Twilio) failed", message=frappe.get_traceback())


def _twilio_number(number, is_whatsapp):
    number = number if number.startswith("+") else f"+{number}"
    return f"whatsapp:{number}" if is_whatsapp else number
