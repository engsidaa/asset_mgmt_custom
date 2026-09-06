"""
Headless API — تطبيق Flutter الميداني (فنيّي/مورِّدي الصيانة)
----------------------------------------------------------------
لا توجد أي شاشات هنا عمداً (توجيه صريح من المستخدم) — فقط نقاط اتصال
برمجية (@frappe.whitelist()) بصيغة JSON قياسية، جاهزة للربط المستقبلي.

**الفرق عن `api/branch_manager.py`:** ذلك الملف مخصص لشخصية "مدير
الفرع" (مُقيَّد تلقائياً بفرعه عبر User Permission — انظر توثيقه هو
لتفاصيل هذه الآلية). هذا الملف مخصص لشخصية "الفني/مورِّد الصيانة
الميداني" — قد يعمل على أكثر من فرع، وتقييده الحقيقي هو "المهام
المُسنَدة إليه تحديداً" (assigned_technician) وليس فرعاً بعينه. حيث
يتداخل الاثنان منطقياً (بيانات الأصل، إنشاء بلاغ عطل)، تُعاد دوال
`branch_manager` مباشرة بدل تكرار نفس المنطق.
"""

import json

import frappe
from frappe import _

from asset_mgmt_custom.api.branch_manager import create_maintenance_request, get_asset_detail


@frappe.whitelist()
def get_branch_assets(branch):
    """
    قائمة أصول فرع معيّن — للفني المُوفَد لفرع لفحص/صيانة أصوله. يعتمد
    فقط على صلاحية قراءة Asset العادية (ممنوحة أصلاً لدور Asset
    Technician)، وليس على User Permission الخاصة بـ Branch (تلك مخصصة
    لمدراء الفروع أنفسهم، وليس فنيّي الصيانة المتنقلين بين عدة فروع).
    """
    return frappe.get_list(
        "Asset",
        filters={
            "custom_branch": branch,
            "docstatus": 1,
            "status": ["not in", ["Scrapped", "Sold"]],
        },
        fields=[
            "name", "asset_name", "asset_category", "location", "status",
            "custom_operational_status", "custom_coding_status", "image",
        ],
        order_by="asset_category, asset_name",
        limit_page_length=0,
    )


def resolve_asset_identifier(identifier):
    """
    مطابقة كود ممسوح (QR/باركود) أو مُدخَل يدوياً إلى اسم أصل حقيقي —
    اسم الأصل نفسه، أو كود الملصق (Barcode/RFID)، أو كود النقش الحديدي
    (Iron Code)، أيهما وُجد أولاً. نقطة المطابقة الوحيدة في هذا التطبيق —
    يُستدعى من scan_asset هنا ومن أدوات المسح الجماعي (Asset Physical
    Audit) بلا تكرار المنطق.
    """
    return (
        frappe.db.get_value("Asset", identifier)
        or frappe.db.get_value("Asset", {"custom_sticker_code": identifier})
        or frappe.db.get_value("Asset", {"custom_iron_code": identifier})
    )


@frappe.whitelist()
def scan_asset(identifier):
    """
    استعلام فوري بمسح كود QR/باركود أو إدخال الكود يدوياً، ثم يُعيد نفس
    تفاصيل الأصل الكاملة المُستخدَمة أصلاً في بوابة مدير الفرع
    (get_asset_detail) — بلا تكرار.
    """
    asset_name = resolve_asset_identifier(identifier)
    if not asset_name:
        frappe.throw(_("No asset found matching '{0}'.").format(identifier))

    return get_asset_detail(asset_name)


@frappe.whitelist()
def create_complaint(asset, problem_description, work_type=None, priority=None, photo_file_url=None):
    """
    بلاغ عطل فوري — يفوِّض بالكامل لنفس create_maintenance_request
    المُستخدَمة في بوابة مدير الفرع (إنشاء + تسليم أمر عمل في استدعاء
    واحد). photo_file_url اختياري: رابط ملف مرفوع مسبقاً عبر
    /api/method/upload_file من قِبل العميل (Base64/Multipart في التطبيق
    نفسه)، يُربَط بحقل fault_photo بعد الإنشاء مباشرة.
    """
    result = create_maintenance_request(
        asset, problem_description, work_type=work_type, priority=priority
    )
    if photo_file_url:
        frappe.db.set_value(
            "Asset Work Order", result["name"], "fault_photo", photo_file_url, update_modified=False
        )
    return result


@frappe.whitelist()
def get_technician_jobs(status=None):
    """
    مهام الصيانة المفتوحة المُسنَدة للمستخدم الحالي تحديداً (فني أو
    مورِّد صيانة خارجي)، مرتبة حسب درجة خطورة الأولوية ثم موعد الاستحقاق
    — تُطبَّق طبقة الصلاحيات القياسية لـ Asset Work Order تلقائياً
    (get_list)، بالإضافة لفلتر assigned_technician الصريح هنا.
    """
    filters = {"assigned_technician": frappe.session.user, "docstatus": 1}
    filters["status"] = status or ["not in", ["مكتمل", "ملغي", "مرفوض"]]

    return frappe.get_list(
        "Asset Work Order",
        filters=filters,
        fields=[
            "name", "title", "asset", "asset_name", "status", "priority", "work_type",
            "request_date", "resolution_due_by", "sla_breached", "problem_description", "fault_photo",
        ],
        order_by="field(priority, 'حرج', 'عاجل', 'متوسط', 'عادي'), resolution_due_by asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def update_job_status(work_order, action, reason=None):
    """
    معالجة (إتمام/رفض) أمر عمل — استدعاء واحد يُفوِّض مباشرة لنفس
    الدوال الموثَّقة والمحمية (complete_work_order/reject_work_order) في
    Asset Work Order، بما فيها كل فحوصات الصلاحية (_check_maintenance_role)
    والترحيل المحاسبي والصرف المخزني التلقائي — بلا أي منطق أعمال مكرر
    هنا.
    """
    doc = frappe.get_doc("Asset Work Order", work_order)
    if action == "complete":
        doc.complete_work_order()
    elif action == "reject":
        doc.reject_work_order(reason)
    else:
        frappe.throw(_("Unknown action '{0}'. Use 'complete' or 'reject'.").format(action))

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def submit_physical_audit(audit_id, items):
    """
    تحديث جماعي (Bulk) لبنود جرد مادي بمسودة Asset Physical Audit موجودة
    بالفعل (أُنشئت وعُبِّئت مبدئياً عبر fetch_assets)، ثم تسليمها —
    بدل إرسال كل بند بنداء API منفصل. items: قائمة
    {asset, audit_result, actual_location?, remarks?}.
    """
    if isinstance(items, str):
        items = json.loads(items)

    doc = frappe.get_doc("Asset Physical Audit", audit_id)
    if doc.docstatus != 0:
        frappe.throw(_("Audit {0} is not in draft status.").format(audit_id))

    rows_by_asset = {row.asset: row for row in doc.items}
    for item in items:
        row = rows_by_asset.get(item.get("asset"))
        if not row:
            continue
        row.audit_result = item.get("audit_result") or row.audit_result
        row.actual_location = item.get("actual_location") or row.actual_location
        row.remarks = item.get("remarks") or row.remarks

    doc.save()
    doc.submit()

    return {
        "name": doc.name,
        "audit_status": doc.audit_status,
        "found_count": doc.found_count,
        "missing_count": doc.missing_count,
        "damaged_count": doc.damaged_count,
    }
