import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class AssetReturnRequest(Document):
    def on_submit(self):
        self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Pending")

    @frappe.whitelist()
    def mark_returned(self):
        """
        كانت هذه الدالة موجودة بلا @frappe.whitelist() — أي بلا أي طريقة
        فعلية لاستدعائها من الواجهة أو الـ API إطلاقاً؛ كود ميت تماماً
        منذ إنشائه. الآن، بالإضافة لتفعيلها: تُغلِق أيضاً سجل Asset
        Employee Allocation المطابق (نفس الأصل + نفس الموظف، حالة
        Active) إن وُجد — بدل ترك حالتين منفصلتين (Return Request
        وEmployee Allocation) قد تتعارضان حول "هل رجع الأصل فعلاً أم لا".
        """
        if self.status != "Approved":
            frappe.throw(_("This request must be Approved before it can be marked as returned."))

        self.db_set("status", "Returned")
        self.db_set("actual_return_date", today())

        allocation = frappe.db.get_value(
            "Asset Employee Allocation",
            {"asset": self.asset, "employee": self.current_custodian, "status": "Active"},
        )
        if allocation:
            frappe.db.set_value("Asset Employee Allocation", allocation, {
                "status": "Returned",
                "return_date": today(),
                "condition_on_return": self._map_condition(),
            }, update_modified=False)
            self.db_set("linked_allocation", allocation, update_modified=False)

    def _map_condition(self):
        # Asset Employee Allocation.condition_on_return يستخدم قائمة أضيق
        # (Good/Damaged/Lost) من Asset Return Request.condition_at_return
        # (Excellent/Good/Fair/Damaged/Beyond Repair) — تحويل بسيط بدل
        # ترك الحقل فارغاً أو رفض التحديث.
        if self.condition_at_return in ("Excellent", "Good", "Fair"):
            return "Good"
        if self.condition_at_return == "Beyond Repair":
            return "Lost"
        return "Damaged"
