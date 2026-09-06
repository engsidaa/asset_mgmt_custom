"""
تفويض صلاحية الاعتماد (Approval Delegation)
---------------------------------------------
طبقة مساعدة مشتركة فوق DocType "Asset Approval Delegate" — تُستخدم من
أي مرحلة اعتماد فردية (سواء بوابة دور وظيفي أو "مستخدم محدد" كمدير فرع)
للسماح لشخص آخر بالتصرف نيابةً خلال فترة محددة (إجازة، مهمة خارجية)،
دون تعديل إعداد الدور أو حقل مدير الفرع نفسه.

يُستخدم حالياً في Asset Requisition (asset_requisition.py) فقط — هي
الوثيقة الوحيدة في هذا التطبيق التي تملك بوابات اعتماد فردية متتالية
(انظر توثيقها الخاص)؛ باقي فحوصات الأدوار في التطبيق مفتوحة لعدة أدوار
معاً (OR) وليست بوابة فردية تحتاج تفويضاً.
"""

import frappe
from frappe.utils import today


def is_delegated_for_role(user, role):
    """هل user مُفوَّض إليه اليوم لتنفيذ اعتماد يشترط الدور role؟"""
    return bool(_active_delegation(user, "دور وظيفي (Role)", role=role))


def is_delegated_for_branch_manager(user, branch):
    """هل user مُفوَّض إليه اليوم للاعتماد بدلاً من مدير الفرع branch؟"""
    if not branch:
        return False
    return bool(_active_delegation(user, "مدير فرع محدد (Branch Manager)", branch=branch))


def _active_delegation(user, delegation_type, role=None, branch=None):
    filters = {
        "delegate": user,
        "delegation_type": delegation_type,
        "from_date": ["<=", today()],
        "to_date": [">=", today()],
    }
    if role:
        filters["role"] = role
    if branch:
        filters["branch"] = branch
    return frappe.db.exists("Asset Approval Delegate", filters)
