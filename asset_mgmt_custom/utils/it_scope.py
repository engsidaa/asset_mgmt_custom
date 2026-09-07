"""
تحديد نطاق "فني تقنية المعلومات" — نقطة واحدة مشتركة
------------------------------------------------------
كل مكان في هذا التطبيق يحتاج يعرف "هل هذا المستخدم فني تقنية معلومات؟"
أو "ما هي فئات الأصول الخاصة بتقنية المعلومات؟" كان يكرر نفس الاستعلام
(get_app_context في mobile.py، التوزيع التلقائي في asset_work_order.py،
تنبيهات تراخيص البرامج في tasks.py). هذا الملف هو المصدر الوحيد الآن
لكلا الفحصين، حتى لا تختلف المعايير بين مكان وآخر بمرور الوقت.

المعيار المستخدَم: Maintenance Team Member.custom_complaint_department
للمستخدم (الفني)، وAsset Category.custom_complaint_department (حقل
مخصص جديد، fixtures/custom_field.json) لفئة الأصل — نفس نص القيمة
الحرفي "تقنية المعلومات" المُستخدَم بالفعل في Asset Work Order.
"""

import frappe

IT_DEPARTMENT_LABEL = "تقنية المعلومات"


def is_it_technician(user=None):
    user = user or frappe.session.user
    return bool(frappe.db.exists(
        "Maintenance Team Member",
        {"team_member": user, "custom_complaint_department": IT_DEPARTMENT_LABEL},
    ))


def get_it_asset_categories():
    return frappe.get_all(
        "Asset Category",
        filters={"custom_complaint_department": IT_DEPARTMENT_LABEL},
        pluck="name",
    )
