import frappe
from frappe.model.document import Document
from frappe import _


class AssetHandover(Document):
    def validate(self):
        self._compute_summary()

    def on_submit(self):
        self.status = "Completed"
        self.db_set("status", "Completed")
        self._log_asset_activities()

    def _compute_summary(self):
        items = self.items or []
        self.total_assets = len(items)
        self.good_count = sum(1 for i in items if i.condition in ("Good", ""))
        self.damaged_count = sum(1 for i in items if i.condition == "Damaged")

    def _log_asset_activities(self):
        # Asset Activity (core ERPNext) has only 4 fields: asset, subject,
        # date, user — لا يوجد activity_type/transaction_date/
        # reference_doctype/reference_docname/notes إطلاقاً. النسخة
        # السابقة كانت بتحاول تضبط حقول غير موجودة، subject (الحقل
        # الإلزامي الوحيد) ما كنش بيتحدد خالص، فكل insert كان بيفشل بخطأ
        # حقل إلزامي مفقود — لكن الخطأ كان بيتبلع بصمت بسبب except:
        # pass، فسجل النشاط ده ما كنش بيتسجل أبداً من غير ما حد يلاحظ.
        for item in self.items:
            if not item.asset:
                continue
            try:
                frappe.get_doc({
                    "doctype": "Asset Activity",
                    "asset": item.asset,
                    "subject": _("Handover from {0} to {1} at branch {2}. Condition: {3}").format(
                        self.outgoing_manager, self.incoming_manager,
                        self.branch, item.condition or "Good"
                    ),
                    "date": self.handover_date or frappe.utils.now_datetime(),
                    "user": frappe.session.user,
                }).insert(ignore_permissions=True, ignore_links=True)
            except Exception:
                frappe.log_error(title="asset_handover: failed to log Asset Activity")


@frappe.whitelist()
def fetch_branch_assets(branch):
    # Asset ماله حقل اسمه serial_no إطلاقاً (لا في ERPNext الأساسي ولا
    # كحقل مخصص هنا) — كان هيفشل بخطأ SQL خام أول ما حد يستخدم هذا الزر.
    # الأقرب لمعنى "الرقم التسلسلي" في هذا التطبيق هو كود التاگ (Sticker
    # لو Barcode/RFID، أو Iron Code لو نقش حديدي).
    return frappe.db.sql("""
        SELECT name, asset_name, asset_category,
               COALESCE(custom_sticker_code, custom_iron_code, '') AS serial_no
        FROM `tabAsset`
        WHERE custom_branch = %(branch)s
          AND docstatus < 2
          AND status NOT IN ('Scrapped', 'Sold')
        ORDER BY asset_category, asset_name
    """, {"branch": branch}, as_dict=True)
