"""
معالج فتح فرع جديد (New Branch Onboarding)
--------------------------------------------
سلسلة مطاعم/أغذية متوسعة (كويت الغذاء) تفتح فروعاً جديدة بشكل متكرر —
كان إعداد الهرمية الكاملة لفرع جديد (Company -> Branch -> Location/
Warehouse -> Cost Center) يتطلب فتح 4 شاشات منفصلة بمعزل عن بعضها
(Cost Center، Warehouse، Location، ثم Branch نفسه لربطها) بدون أي رابط
تلقائي بينها. هذه الدالة الواحدة تُنشئ الأربعة معاً (أو تربط بموجود
منها حسب اختيار المستخدم) في نداء واحد.

الشجرية (Cost Center/Warehouse) تتطلب أباً (parent) — يُكتَشَف تلقائياً
كأول مجموعة جذر لنفس الشركة (root)، ويبقى قابلاً للتغيير يدوياً لاحقاً
من شاشة كل مستند بعد الإنشاء لو الافتراضي غير مناسب.
"""

import frappe
from frappe import _


def _detect_root(doctype, company=None):
    filters = {"is_group": 1}
    if company:
        filters["company"] = company
    return frappe.db.get_value(doctype, filters, "name", order_by="lft asc")


@frappe.whitelist()
def onboard_new_branch(
    branch_name,
    company,
    territory=None,
    branch_manager=None,
    create_cost_center=1,
    cost_center=None,
    create_warehouse=1,
    warehouse=None,
    create_location=1,
    location=None,
):
    if frappe.db.exists("Branch", branch_name):
        frappe.throw(_("Branch {0} already exists.").format(branch_name))

    create_cost_center = int(create_cost_center)
    create_warehouse = int(create_warehouse)
    create_location = int(create_location)

    created = {}

    try:
        if create_cost_center:
            parent_cost_center = _detect_root("Cost Center", company)
            if not parent_cost_center:
                frappe.throw(
                    _("No root Cost Center found for company {0}. Please create one first, "
                      "or untick 'Create Cost Center' and select an existing one.").format(company)
                )
            cc = frappe.new_doc("Cost Center")
            cc.cost_center_name = branch_name
            cc.company = company
            cc.parent_cost_center = parent_cost_center
            cc.insert(ignore_permissions=True)
            cost_center = cc.name
            created["cost_center"] = cost_center
        elif not cost_center:
            frappe.throw(_("Please select an existing Cost Center, or tick 'Create Cost Center'."))

        if create_warehouse:
            parent_warehouse = _detect_root("Warehouse", company)
            wh = frappe.new_doc("Warehouse")
            wh.warehouse_name = branch_name
            wh.company = company
            if parent_warehouse:
                wh.parent_warehouse = parent_warehouse
            wh.insert(ignore_permissions=True)
            warehouse = wh.name
            created["warehouse"] = warehouse
        elif not warehouse:
            frappe.throw(_("Please select an existing Warehouse, or tick 'Create Warehouse'."))

        if create_location:
            loc = frappe.new_doc("Location")
            loc.location_name = branch_name
            loc.insert(ignore_permissions=True)
            location = loc.name
            created["location"] = location
        elif not location:
            frappe.throw(_("Please select an existing Location, or tick 'Create Location'."))

        branch = frappe.new_doc("Branch")
        branch.branch = branch_name
        branch.custom_cost_center = cost_center
        branch.custom_default_warehouse = warehouse
        branch.custom_default_location = location
        if territory:
            branch.custom_territory = territory
        if branch_manager:
            branch.custom_branch_manager = branch_manager
        branch.insert(ignore_permissions=True)
        created["branch"] = branch.name

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="onboard_new_branch failed", message=frappe.get_traceback())
        raise

    return created
