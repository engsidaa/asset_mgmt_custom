import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, now_datetime

RATING_PERIOD_DAYS = {
    "ربع سنوي": 90,
    "نصف سنوي": 182,
    "سنوي": 365,
}


class AssetVendorPerformanceRating(Document):
    def before_save(self):
        scores = [
            self.response_time_score or 0,
            self.quality_score or 0,
            self.timeliness_score or 0,
            self.pricing_score or 0,
            self.communication_score or 0,
        ]
        filled = [s for s in scores if s]
        self.overall_score = round(sum(filled) / len(filled), 2) if filled else 0

    @frappe.whitelist()
    def compute_from_work_orders(self):
        """
        يملأ response_time_score وtimeliness_score من بيانات Asset Work
        Order الفعلية المرتبطة بعقود هذا المورد (عقد واحد إن كان الحقل
        'contract' محدداً، أو كل عقود المورد إن لم يكن) — بدل تقييم ذاتي
        بحت. باقي المعايير (جودة/تسعير/تواصل) لا يوجد لها مقياس بيانات
        فعلي في هذا التطبيق فتبقى يدوية عمداً.
        """
        if not self.supplier:
            frappe.throw(_("Please set the Supplier first."))

        period_days = RATING_PERIOD_DAYS.get(self.rating_period, 90)
        from_date = add_days(self.rating_date or now_datetime(), -period_days)

        contract_filters = {"supplier": self.supplier}
        if self.contract:
            contract_filters = {"name": self.contract}
        contracts = frappe.get_all("Asset Vendor Contract", filters=contract_filters, pluck="name")
        if not contracts:
            frappe.throw(_("No Asset Vendor Contract found for supplier {0}.").format(self.supplier))

        rows = frappe.db.sql("""
            SELECT wo.name, wo.request_date, wo.completion_date, wo.sla_breached,
                   vc.sla_response_hours
            FROM `tabAsset Work Order` wo
            JOIN `tabAsset Vendor Contract` vc ON vc.name = wo.vendor_contract
            WHERE wo.vendor_contract IN %(contracts)s
              AND wo.docstatus < 2
              AND wo.status = 'مكتمل'
              AND wo.request_date >= %(from_date)s
              AND wo.request_date <= %(to_date)s
        """, {
            "contracts": contracts,
            "from_date": from_date,
            "to_date": self.rating_date,
        }, as_dict=True)

        if not rows:
            frappe.msgprint(
                _("No completed work orders found for this supplier in the selected period — "
                  "scores were not changed."),
                alert=True, indicator="orange",
            )
            return

        breach_count = sum(1 for r in rows if r.sla_breached)
        breach_rate = breach_count / len(rows)

        response_ratios = []
        actual_hours_list = []
        for r in rows:
            if not r.completion_date or not r.request_date:
                continue
            actual_hours = (
                frappe.utils.get_datetime(r.completion_date) - frappe.utils.get_datetime(r.request_date)
            ).total_seconds() / 3600
            actual_hours_list.append(actual_hours)
            if r.sla_response_hours:
                response_ratios.append(actual_hours / r.sla_response_hours)

        avg_ratio = sum(response_ratios) / len(response_ratios) if response_ratios else None
        avg_hours = flt(sum(actual_hours_list) / len(actual_hours_list), 2) if actual_hours_list else None

        # الالتزام بالمواعيد: 0% خرق = 5، 100% خرق = 1 (مقياس خطي)
        self.timeliness_score = max(1, min(5, round(5 - breach_rate * 4)))

        # سرعة الاستجابة: تنفيذ بمتوسط ≤ زمن SLA المتفق عليه = 5، وكل ضعف
        # إضافي لزمن SLA يخصم نقطة، حتى الحد الأدنى 1
        if avg_ratio is not None:
            self.response_time_score = max(1, min(5, round(5 - max(avg_ratio - 1, 0) * 4)))

        self.computed_work_order_count = len(rows)
        self.computed_sla_breach_rate = flt(breach_rate * 100, 2)
        self.computed_avg_response_hours = avg_hours
        self.computed_on = now_datetime()

        return {
            "work_order_count": self.computed_work_order_count,
            "sla_breach_rate": self.computed_sla_breach_rate,
            "avg_response_hours": self.computed_avg_response_hours,
            "timeliness_score": self.timeliness_score,
            "response_time_score": self.response_time_score,
        }
