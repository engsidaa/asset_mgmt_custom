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
        """
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
