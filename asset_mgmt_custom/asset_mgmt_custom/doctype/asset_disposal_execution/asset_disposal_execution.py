import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class AssetDisposalExecution(Document):
    def on_submit(self):
        self.db_set("disposal_status", "Executed")
        if self.disposal_request:
            # "Asset Disposal Request" ماله حقل اسمه workflow_state —
            # حقل حالته الحقيقي هو status (Draft/Pending Approval/Approved/
            # Rejected، مفيش حالة "Executed" أصلاً هناك — التنفيذ متتبَّع
            # بالكامل في disposal_status هنا). كان هيفشل بخطأ SQL خام أول
            # ما ينفَّذ أي تصرف.
            frappe.db.set_value(
                "Asset Disposal Request",
                self.disposal_request,
                "status",
                "Approved",
                update_modified=False
            )
        self._execute_financial_disposal()

    def _execute_financial_disposal(self):
        """
        قبل هذا التعديل: تسليم "Asset Disposal Execution" كان يُسجِّل
        الحدث فقط (نموذج/تاريخ/طريقة تخلص) بدون أي أثر محاسبي إطلاقاً —
        لا قيد يومية، ولا حتى تحديث حالة الأصل نفسه (status/disposal_date)
        في ERPNext. كان الأصل يبقى "Submitted" إلى الأبد رغم التخلص منه
        فعلياً وتوثيق ذلك هنا، فيظل يُحتسَب ضمن الأصول النشطة في كل تقرير.

        الإصلاح: يستدعي آليات ERPNext الأساسية الحقيقية لكل حالة — بدل
        اختراع محاسبة تخلص جديدة قد تتصادم معها:
        - Scrapped/Destroyed/Donated (لا قيمة بيع حقيقية): يستدعي
          erpnext...depreciation.scrap_asset() مباشرة — نفس الدالة التي
          يستدعيها زر "Scrap Asset" على نموذج الأصل نفسه (إهلاك نهائي +
          قيد إقفال الأصل تلقائياً).
        - Sold/Auctioned (فيه قيمة بيع فعلية): يُنشئ فاتورة بيع (Sales
          Invoice) كمسودة عبر erpnext...asset.make_sales_invoice() —
          نفس الدالة التي يستدعيها زر "Sell Asset" — ويترك تسليمها
          لفريق المالية يدوياً (لازم تحديد العميل/الضريبة أولاً، قرار
          بشري وليس تلقائياً).
        """
        asset = frappe.get_doc("Asset", self.asset)
        if asset.status in ("Scrapped", "Sold"):
            return

        if self.disposal_method in ("Scrapped", "Destroyed", "Donated"):
            # scrap_asset() الأساسي يضبط disposal_date/journal_entry_for_scrap
            # وحالة الأصل والقيد المحاسبي بنفسه بالكامل — لا حاجة لتكرار أي
            # من ذلك هنا.
            from erpnext.assets.doctype.asset.depreciation import scrap_asset
            scrap_asset(self.asset)

        elif self.disposal_method in ("Sold", "Auctioned"):
            if not asset.item_code:
                frappe.throw(
                    _("Asset {0} has no linked Item Code — cannot create a Sales Invoice for it.").format(asset.name)
                )
            from erpnext.assets.doctype.asset.asset import make_sales_invoice
            si = make_sales_invoice(self.asset, asset.item_code, asset.company)
            if self.get("actual_sale_value"):
                for item in si.items:
                    item.rate = self.actual_sale_value
                    item.amount = self.actual_sale_value
            si.posting_date = self.execution_date or today()
            si.insert(ignore_permissions=True)
            self.db_set("sales_invoice", si.name)
            frappe.msgprint(
                _("Draft Sales Invoice {0} created — set the buyer and tax details and submit it "
                  "to complete the sale accounting.").format(si.name),
                alert=True, indicator="blue",
            )

    def on_cancel(self):
        self.db_set("disposal_status", "Cancelled")
        self._reverse_financial_disposal()

    def _reverse_financial_disposal(self):
        asset_status = frappe.db.get_value("Asset", self.asset, "status")

        if asset_status == "Scrapped" and not self.get("sales_invoice"):
            from erpnext.assets.doctype.asset.depreciation import restore_asset
            restore_asset(self.asset)

        if self.get("sales_invoice") and frappe.db.exists("Sales Invoice", self.sales_invoice):
            si_docstatus = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
            if si_docstatus == 0:
                frappe.delete_doc("Sales Invoice", self.sales_invoice, ignore_permissions=True)
            else:
                frappe.msgprint(
                    _("Sales Invoice {0} was already submitted — it was NOT reversed automatically. "
                      "Please handle the sale reversal (credit note) manually if needed.").format(self.sales_invoice),
                    alert=True, indicator="orange",
                )
