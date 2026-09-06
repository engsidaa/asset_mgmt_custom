"""
Headless API — استقبال قراءات أجهزة استشعار IoT دفعياً
----------------------------------------------------------
توجيه صريح من المستخدم: بدون أي منطق جديد لحدود السلامة هنا — هذا
الملف **يُنشئ فقط** سجلات Asset Meter Reading حقيقية من الدفعة الواردة،
والتحقق من حدود الأمان (سلسلة التبريد) وإنشاء أمر العمل الطارئ تلقائياً
يحدث بالفعل داخل Asset Meter Reading.after_insert() ->
_check_temperature_threshold() — منطق موجود مسبقاً بالكامل (Phase 4)،
ولا يُكرَّر هنا إطلاقاً.

**المصادقة (Auth):** لا يوجد أي آلية Token مخصصة مبنية هنا — تُستخدم
آلية Frappe الأصلية REST API Key/Secret: أنشئ مستخدماً مخصصاً (مثال:
"iot-gateway@kuwaitfood.internal") بدور محدود (Asset Technician فقط)،
ولِّد له API Key + API Secret من شاشة المستخدم، واجعل بوابة/جهاز IoT
يرسل الطلب برأس HTTP:
    Authorization: token <api_key>:<api_secret>
Frappe يرفض أي طلب بلا هذا الرأس (أو بمفتاح خاطئ) **قبل** وصوله لهذه
الدالة إطلاقاً — إعادة بناء تحقق Token هنا كانت ستُكرِّر مصادقة Core
الأصلية دون داعٍ ومخاطرة أمنية إضافية بلا مبرر.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

PARAMETER_TO_METER_TYPE = {
    "temperature": "درجة الحرارة",
    "درجة الحرارة": "درجة الحرارة",
    "operating_hours": "ساعات تشغيل",
    "ساعات تشغيل": "ساعات تشغيل",
    "odometer": "كيلومترات",
    "كيلومترات": "كيلومترات",
    "production_units": "وحدات إنتاج",
    "وحدات إنتاج": "وحدات إنتاج",
    "fuel_liters": "لتر وقود",
    "لتر وقود": "لتر وقود",
}


@frappe.whitelist()
def ingest_readings(readings):
    """
    نقطة الاستقبال الدفعية الوحيدة. الصيغة المتوقعة (JSON، أو قائمة
    Python بالفعل إن استُدعيت داخلياً):
        [{"asset": "AST-001", "parameter": "temperature", "value": 8.5,
          "timestamp": "2026-01-01 14:30:00"}, ...]
    كل قراءة تُعالَج وتُسجَّل بشكل مستقل — فشل قراءة واحدة (أصل غير
    موجود، معامل غير معروف...) لا يُسقِط باقي الدفعة، بل يُسجَّل كخطأ
    في نتيجتها فقط.
    """
    if isinstance(readings, str):
        readings = json.loads(readings)

    return [_ingest_one_reading(reading) for reading in readings]


def _ingest_one_reading(reading):
    asset = reading.get("asset")
    parameter = reading.get("parameter")
    value = reading.get("value")
    timestamp = reading.get("timestamp")

    if not asset or not parameter or value is None:
        return {"asset": asset, "status": "error", "message": "Missing 'asset', 'parameter', or 'value'."}

    meter_type = PARAMETER_TO_METER_TYPE.get(parameter)
    if not meter_type:
        return {"asset": asset, "status": "error", "message": f"Unknown telemetry parameter '{parameter}'."}

    if not frappe.db.exists("Asset", asset):
        return {"asset": asset, "status": "error", "message": f"Asset {asset} not found."}

    reading_date = get_datetime(timestamp) if timestamp else now_datetime()
    value_fieldname = "temperature_celsius" if meter_type == "درجة الحرارة" else "current_reading"

    # حماية ضد التكرار: نفس الأصل/النوع/الطابع الزمني الكامل (لحظة
    # بالثانية، وليس يوماً فقط — reading_date أصبح Datetime عمداً)/القيمة
    # بالضبط — سيناريو واقعي عند إعادة إرسال شبكية لنفس الحزمة من بوابة
    # IoT. قبل هذا التعديل كان reading_date تاريخاً فقط (بلا وقت)، فكانت
    # قراءات متكررة مشروعة بنفس القيمة المستقرة (مثال: سلسلة تبريد ثابتة
    # عند 4.0°م كل 5 دقائق طوال اليوم) تُصنَّف خطأً كتكرار وتُرفَض بعد أول
    # قراءة في اليوم — يحرم ذلك إثبات استمرارية عمل الحساس زمنياً.
    duplicate = frappe.db.exists("Asset Meter Reading", {
        "asset": asset,
        "meter_type": meter_type,
        "reading_date": reading_date,
        value_fieldname: flt(value),
    })
    if duplicate:
        return {"asset": asset, "status": "duplicate", "meter_reading": duplicate}

    try:
        doc = frappe.new_doc("Asset Meter Reading")
        doc.asset = asset
        doc.meter_type = meter_type
        doc.reading_date = reading_date
        doc.read_by = frappe.session.user
        doc.notes = _("Auto-ingested via IoT telemetry endpoint")
        doc.set(value_fieldname, flt(value))
        doc.insert(ignore_permissions=True)
        return {"asset": asset, "status": "ok", "meter_reading": doc.name}
    except Exception:
        frappe.log_error(title="IoT telemetry ingestion failed", message=frappe.get_traceback())
        return {"asset": asset, "status": "error", "message": "Internal error — see Error Log."}
