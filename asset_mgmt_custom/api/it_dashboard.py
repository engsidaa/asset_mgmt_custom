"""
لوحة مؤشرات تقنية المعلومات — مقاييس خاصة بشكاوى/طلبات "تقنية المعلومات"
معزولة عن مقاييس الصيانة العامة (Asset Work Order.complaint_department ==
"تقنية المعلومات")، بالإضافة لتراخيص البرامج المقتربة من الانتهاء
(Asset Software License). صفحة Desk واحدة (انظر page/it_support_dashboard)
تستدعي get_it_dashboard_summary() هذه في استدعاء واحد.
"""

import frappe
from frappe.utils import add_days, today


@frappe.whitelist()
def get_it_dashboard_summary():
    open_it = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabAsset Work Order`
        WHERE complaint_department = 'تقنية المعلومات'
          AND docstatus < 2
          AND status NOT IN ('مكتمل', 'ملغي', 'مرفوض')
    """)[0][0]

    open_general = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabAsset Work Order`
        WHERE (asset IS NOT NULL AND asset != '' OR complaint_department = 'صيانة عامة')
          AND docstatus < 2
          AND status NOT IN ('مكتمل', 'ملغي', 'مرفوض')
    """)[0][0]

    overdue_it = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabAsset Work Order`
        WHERE complaint_department = 'تقنية المعلومات'
          AND docstatus < 2
          AND status NOT IN ('مكتمل', 'ملغي', 'مرفوض')
          AND (sla_breached = 1 OR (resolution_due_by IS NOT NULL AND resolution_due_by < NOW()))
    """)[0][0]

    full_outage_open = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabAsset Work Order`
        WHERE complaint_department = 'تقنية المعلومات'
          AND it_full_outage = 1
          AND docstatus < 2
          AND status NOT IN ('مكتمل', 'ملغي', 'مرفوض')
    """)[0][0]

    avg_resolution = frappe.db.sql("""
        SELECT
            AVG(CASE WHEN complaint_department = 'تقنية المعلومات'
                     THEN TIMESTAMPDIFF(HOUR, creation, completion_date) END) AS it_hours,
            AVG(CASE WHEN complaint_department != 'تقنية المعلومات' OR complaint_department IS NULL
                     THEN TIMESTAMPDIFF(HOUR, creation, completion_date) END) AS other_hours
        FROM `tabAsset Work Order`
        WHERE status = 'مكتمل'
          AND completion_date IS NOT NULL
          AND creation >= DATE_SUB(NOW(), INTERVAL 90 DAY)
    """, as_dict=True)[0]

    top_device_types = frappe.db.sql("""
        SELECT it_device_type, COUNT(*) AS total
        FROM `tabAsset Work Order`
        WHERE complaint_department = 'تقنية المعلومات'
          AND it_device_type IS NOT NULL AND it_device_type != ''
          AND creation >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        GROUP BY it_device_type
        ORDER BY total DESC
        LIMIT 5
    """, as_dict=True)

    expiring_licenses = frappe.db.sql("""
        SELECT name, software_name, vendor, expiry_date, asset_name
        FROM `tabAsset Software License`
        WHERE expiry_date BETWEEN %(today)s AND %(cutoff)s
          AND status NOT IN ('Expired', 'Terminated')
        ORDER BY expiry_date ASC
    """, {"today": today(), "cutoff": add_days(today(), 30)}, as_dict=True)

    return {
        "open_it_complaints": open_it,
        "open_general_complaints": open_general,
        "overdue_it_complaints": overdue_it,
        "full_outage_open": full_outage_open,
        "avg_resolution_hours_it": round(avg_resolution.it_hours, 1) if avg_resolution.it_hours else None,
        "avg_resolution_hours_other": round(avg_resolution.other_hours, 1) if avg_resolution.other_hours else None,
        "top_device_types": top_device_types,
        "expiring_licenses": expiring_licenses,
    }
