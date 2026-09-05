"""
Branch override
---------------
Branch.custom_branch_manager هو مصدر الحقيقة الوحيد لمن هو "مدير" هذا
الفرع. أي تغيير عليه (تعيين مدير جديد، تغييره، أو إزالته) لازم ينعكس
فوراً على صلاحيات الرؤية الفعلية (User Permission) بدل انتظار مزامنة
يدوية — غير كده، مدير فرع سابق هيفضل شايف بيانات فرع مش بتاعه بعد ما
يتغير، ومدير جديد مش هيشوف حاجة لحد ما حد يفتكر يشغّل سكريبت يدوي.

User Permission بمفردها لا تكفي: هي تُقيِّد الرؤية فقط لمن يملك أصلاً
صلاحية أساسية (Role) على الـ DocType — فبدون دور "Branch Manager"
معيَّن للمستخدم، صلاحية User Permission بلا أثر. لذلك هذا الهوك يضمن
الاثنين معاً: الدور (يُضاف تلقائياً، لا يُزال تلقائياً أبداً — إزالته
قرار إداري يدوي فقط) وUser Permission (تُضاف وتُزال تلقائياً حسب حالة
الفرع الحالية).
"""

import frappe


def on_update(doc, method=None):
    sync_branch_manager_permission(doc.name)


def sync_branch_manager_permission(branch_name):
    manager = frappe.db.get_value("Branch", branch_name, "custom_branch_manager")

    existing = frappe.get_all(
        "User Permission",
        filters={"allow": "Branch", "for_value": branch_name},
        fields=["name", "user"],
    )

    # امسح أي صلاحية رؤية باقية لمستخدم لم يعد مدير هذا الفرع تحديداً
    # (تغيّر المدير أو أُزيل) — لا تمسّ صلاحياته على فروع أخرى يديرها.
    for row in existing:
        if row.user != manager:
            frappe.delete_doc(
                "User Permission", row.name, ignore_permissions=True, force=True
            )

    if not manager or not frappe.db.exists("User", manager):
        return

    already_has_permission = any(row.user == manager for row in existing)
    if not already_has_permission:
        frappe.get_doc({
            "doctype": "User Permission",
            "user": manager,
            "allow": "Branch",
            "for_value": branch_name,
            "apply_to_all_doctypes": 1,
        }).insert(ignore_permissions=True)

    user = frappe.get_doc("User", manager)
    if "Branch Manager" not in {r.role for r in user.get("roles")}:
        user.add_roles("Branch Manager")
