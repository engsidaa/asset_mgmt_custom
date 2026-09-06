import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

LOTO_CHECKLIST_FIELDS = (
    "energy_source_identified",
    "equipment_deenergized",
    "lockout_applied",
    "tagout_applied",
    "zero_energy_verified",
    "ppe_confirmed",
)


class AssetWorkPermit(Document):
    def on_submit(self):
        self.db_set("status", "صالح")

    def on_cancel(self):
        self.db_set("status", "ملغي")

    @frappe.whitelist()
    def complete_loto_checklist(self):
        """
        "توقيع إلكتروني" هنا يعني: تسجيل هوية المستخدم الذي أكَّد اكتمال
        كل خطوات العزل + الوقت، عبر استدعاء صريح (وليس مجرد وضع علامة على
        حقل عادي) — بنفس نمط mark_coded()/set_operational() في هذا
        التطبيق. يُشترَط اكتمال كل خطوات القائمة أولاً.

        فصل الصلاحيات (Segregation of Duties): يُشترَط دور "Safety
        Inspector" أو "System Manager" (دعم إداري)، أو مدير الفرع
        المحدَّد فعلياً لفرع هذا الأصل (Branch.custom_branch_manager) —
        لولا هذا الشرط، كان أي فني (Asset Technician، وهو نفسه من يملك
        صلاحية الكتابة على هذا المستند ونفَّذ خطوات العزل غالباً) يقدر
        يوقِّع على عزل قام هو نفسه بتنفيذه، مما يُبطِل الغرض الأساسي من
        توقيع LOTO (تحقق طرف مستقل).
        """
        roles = frappe.get_roles()
        if "Safety Inspector" not in roles and "System Manager" not in roles:
            branch = frappe.db.get_value("Asset", self.asset, "custom_branch")
            branch_manager = frappe.db.get_value("Branch", branch, "custom_branch_manager") if branch else None
            if frappe.session.user != branch_manager:
                frappe.throw(
                    _("Only a Safety Inspector, System Manager, or this asset's designated Branch Manager can "
                      "sign off on a LOTO checklist — the technician who performed the isolation cannot verify "
                      "their own work."),
                    title=_("Not Authorized"),
                )

        if not self.requires_loto:
            frappe.throw(_("This permit is not marked as requiring energy isolation (LOTO)."))

        missing = [f for f in LOTO_CHECKLIST_FIELDS if not self.get(f)]
        if missing:
            frappe.throw(
                _("Please complete all isolation steps before signing off: {0}").format(", ".join(missing)),
                title=_("LOTO Checklist Incomplete"),
            )

        self.db_set("loto_verified", 1, update_modified=False)
        self.db_set("loto_verified_by", frappe.session.user, update_modified=False)
        self.db_set("loto_verified_on", now_datetime(), update_modified=False)
        return "verified"
