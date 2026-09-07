"""
إرسال تنبيهات Push حقيقية عبر Firebase Cloud Messaging (HTTP v1 API) —
تصل حتى والتطبيق مغلق تماماً على الجهاز، خلافاً لتنبيه Notification Log
العادي الذي يحتاج التطبيق مفتوحاً/بالخلفية على الأقل ليقرأه.

الإعداد المطلوب على الخادم (خارج هذا الكود، لمرة واحدة، من يملك وصول SSH):
1. إنشاء مشروع Firebase (من https://console.firebase.google.com) وإضافة
   تطبيق أندرويد بحزمة "com.hosetia.asset_mgmt_mobile".
2. من إعدادات المشروع → Service Accounts → "Generate new private key" —
   يُنزِّل ملف JSON. يُوضَع هذا الملف على السيرفر في مسار خاص **خارج
   نطاق git تماماً** (مثلاً داخل مجلد sites/<site>/private/)، ثم يُسجَّل
   مساره عبر:
       bench --site <site> set-config fcm_service_account_path \
           /full/path/to/service-account.json
   بلا هذا الإعداد، send_push() تتجاهل الإرسال بصمت (لا تُعطِّل أي شيء
   آخر في التطبيق — التنبيه داخل التطبيق يبقى يعمل دائماً بغض النظر).
"""

import frappe

_ACCESS_TOKEN_CACHE_KEY = "fcm_access_token"


def _get_credentials():
    path = frappe.conf.get("fcm_service_account_path")
    if not path:
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError:
        frappe.log_error(
            title="FCM push skipped — google-auth not installed",
            message="pip install google-auth to enable Firebase Cloud Messaging push.",
        )
        return None

    try:
        credentials = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        credentials.refresh(Request())
        return credentials
    except Exception:
        frappe.log_error(title="FCM: failed to load service account credentials", message=frappe.get_traceback())
        return None


def send_push(user, title, body, data=None):
    """
    يُرسَل بصمت (لا يرفع استثناء أبداً للمستدعي) — فشل التوصيل لجهاز واحد
    لا يجب أن يُسقِط أي عملية أعمال حقيقية في التطبيق (إنشاء أمر عمل،
    اعتماد طلب...) التي تستدعي هذه الدالة كأثر جانبي فقط عبر notify_user.
    """
    token = frappe.db.get_value("User", user, "custom_fcm_token")
    if not token:
        return

    credentials = _get_credentials()
    if not credentials:
        return

    try:
        import requests

        url = f"https://fcm.googleapis.com/v1/projects/{credentials.project_id}/messages:send"
        payload = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {str(k): str(v) for k, v in (data or {}).items()},
                "android": {"priority": "high"},
            }
        }
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code == 404 or (
            response.status_code == 400 and "UNREGISTERED" in response.text
        ):
            # التوكن لم يعد صالحاً (تطبيق أُزيل أو أُعيد تثبيته على الجهاز) —
            # نمسحه حتى لا تُعاد محاولة إرسال فاشلة لكل تنبيه لاحق بلا داعٍ.
            frappe.db.set_value("User", user, "custom_fcm_token", None, update_modified=False)
        elif response.status_code >= 400:
            frappe.log_error(
                title="FCM push failed",
                message=f"user={user} status={response.status_code} body={response.text[:500]}",
            )
    except Exception:
        frappe.log_error(title="FCM push failed", message=frappe.get_traceback())
