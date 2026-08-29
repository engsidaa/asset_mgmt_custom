"""
Asset Requisition — مصفوفة اعتماد من 3 مراحل متتالية
-----------------------------------------------------
لا تُستخدم آلية Frappe Workflow هنا (خلافاً لباقي مستندات التطبيق) لأن
المرحلة الثانية تشترط موافقة "شخص محدد لكل فرع" (مدير الفرع)، وWorkflow
الأساسي في Frappe يدعم فقط بوابات على مستوى الدور (Role) — لا يدعم
"المستخدم المحدد في حقل مستند آخر". لذلك الحالة (status) وثلاث دوال
اعتماد مُصرَّح بها (whitelisted) هي آلية التتبع الكاملة، بنفس النمط
المُستخدم بالفعل في overrides/asset.py (mark_coded / set_operational).

تسلسل الاعتماد:
    Draft
      → (تقديم/Submit) → Pending Finance Approval
      → (approve_finance، دور Asset Finance Manager) → Pending Branch Manager Approval
      → (approve_branch_manager، المستخدم المحدد في مدير الفرع) → Pending Asset Manager Approval
      → (approve_asset_manager، دور Asset Manager) → Approved

الرفض (reject) متاح في أي مرحلة "Pending" لصاحب الصلاحية في تلك المرحلة
تحديداً — يضبط الحالة "Rejected" مع السبب والمُرفِض، ويبقى المستند
submitted (بدون إلغاء تلقائي، تفادياً لتعقيد صلاحيات الإلغاء). لإعادة
التقديم: يقوم Asset Manager أو System Manager (ولديهما صلاحية الإلغاء
والتعديل أصلاً) بإلغاء المستند يدوياً ثم استخدام زر "Amend" القياسي في
Frappe.

System Manager مخوَّل بتجاوز أي مرحلة (دعم إداري)، بنفس صلاحياته
الكاملة الموجودة أصلاً على هذا المستند.
"""

import frappe
from frappe import _
from frappe.utils import today, now_datetime
from frappe.model.document import Document


APPROVAL_CHAIN = {
    "Pending Finance Approval": "finance",
    "Pending Branch Manager Approval": "branch_manager",
    "Pending Asset Manager Approval": "asset_manager",
}


class AssetRequisition(Document):
    def validate(self):
        self._check_spare_availability()
        self._check_warehouse_stock()

    def on_submit(self):
        self.db_set("status", "Pending Finance Approval")

    def _check_spare_availability(self):
        """أعلى أولوية: أصل جاهز فعلاً (مُرمَّز، جزء من سجل الأصول) في نفس الفئة."""
        if not self.asset_category:
            return
        filters = {
            "asset_category": self.asset_category,
            "custom_is_spare": 1,
            "docstatus": 1,
        }
        if self.item_code:
            filters["item_code"] = self.item_code
        spare = frappe.db.get_value("Asset", filters, "name")
        if spare:
            self.spare_available = 1
            self.spare_asset = spare
        else:
            self.spare_available = 0
            self.spare_asset = None

    def _check_warehouse_stock(self):
        """
        تحقق فعلي من المخزون (Bin.actual_qty) — يعمل فقط لو مفيش أصل احتياطي
        جاهز أصلاً، وفيه صنف (item_code) ومخزن افتراضي مُعرَّف للفرع.
        هذا تحقق/عرض معلومات فقط لدعم قرار المعتمدين — تحويل الصنف من
        المخزون إلى أصل مُسجَّل فعلياً يبقى إجراء منفصل يقوم به أمين
        المخزن/إدارة الأصول يدوياً بعد الاعتماد، بنفس الآلية المحاسبية
        القياسية في ERPNext (Purchase Receipt → Create Asset)، بدل ما
        نخترع مسار محاسبي جديد.
        """
        self.stock_available = 0
        self.available_qty = 0
        self.check_warehouse = None

        if self.spare_available or not self.item_code or not self.branch:
            return

        warehouse = frappe.db.get_value("Branch", self.branch, "custom_default_warehouse")
        if not warehouse:
            return

        self.check_warehouse = warehouse
        actual_qty = frappe.db.get_value(
            "Bin", {"item_code": self.item_code, "warehouse": warehouse}, "actual_qty"
        ) or 0
        self.available_qty = actual_qty

        required_qty = self.quantity or 1
        if actual_qty >= required_qty:
            self.stock_available = 1

    # ------------------------------------------------------------------
    # المرحلة 1: اعتماد المالية
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def approve_finance(self):
        self._check_stage("Pending Finance Approval", "Asset Finance Manager")
        self.db_set({
            "approved_by_finance": frappe.session.user,
            "finance_approved_on": now_datetime(),
            "status": "Pending Branch Manager Approval",
        })
        return self.status

    # ------------------------------------------------------------------
    # المرحلة 2: اعتماد مدير الفرع (شخص محدد، وليس دوراً عاماً)
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def approve_branch_manager(self):
        if self.status != "Pending Branch Manager Approval":
            frappe.throw(
                _("This requisition is not currently at the Branch Manager approval stage."),
                title=_("Wrong Stage"),
            )
        if not self._is_system_manager():
            if not self.branch_manager:
                frappe.throw(
                    _(
                        "No Branch Manager is configured for Branch {0}. "
                        "Please set 'مدير الفرع (Branch Manager)' on the Branch record first."
                    ).format(self.branch),
                    title=_("Branch Manager Not Configured"),
                )
            if frappe.session.user != self.branch_manager:
                frappe.throw(
                    _("Only the designated Branch Manager ({0}) can approve this stage.").format(
                        self.branch_manager
                    ),
                    title=_("Not Authorized"),
                )
        self.db_set({
            "approved_by_branch_manager": frappe.session.user,
            "branch_manager_approved_on": now_datetime(),
            "status": "Pending Asset Manager Approval",
        })
        return self.status

    # ------------------------------------------------------------------
    # المرحلة 3: اعتماد إدارة الأصول (نهائي)
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def approve_asset_manager(self):
        self._check_stage("Pending Asset Manager Approval", "Asset Manager")
        self.db_set({
            "approved_by_asset_manager": frappe.session.user,
            "asset_manager_approved_on": now_datetime(),
            "status": "Approved",
        })
        return self.status

    # ------------------------------------------------------------------
    # الرفض — في أي مرحلة، بواسطة صاحب الصلاحية في تلك المرحلة تحديداً
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def reject(self, reason):
        if self.status not in APPROVAL_CHAIN:
            frappe.throw(
                _("This requisition is not currently pending any approval."),
                title=_("Nothing to Reject"),
            )
        if not reason or not reason.strip():
            frappe.throw(_("Please provide a rejection reason."))

        stage = APPROVAL_CHAIN[self.status]
        if stage == "finance":
            self._check_stage(self.status, "Asset Finance Manager")
        elif stage == "asset_manager":
            self._check_stage(self.status, "Asset Manager")
        elif stage == "branch_manager" and not self._is_system_manager():
            if not self.branch_manager or frappe.session.user != self.branch_manager:
                frappe.throw(
                    _("Only the designated Branch Manager can reject at this stage."),
                    title=_("Not Authorized"),
                )

        self.db_set({
            "status": "Rejected",
            "rejection_reason": reason,
            "rejected_by": frappe.session.user,
        })
        return self.status

    # ------------------------------------------------------------------
    # مساعدات الصلاحيات
    # ------------------------------------------------------------------

    def _check_stage(self, expected_status, required_role):
        if self.status != expected_status:
            frappe.throw(
                _("This requisition is not currently at the {0} stage.").format(expected_status),
                title=_("Wrong Stage"),
            )
        if required_role not in frappe.get_roles() and not self._is_system_manager():
            frappe.throw(
                _("You need the '{0}' role to act at this stage.").format(required_role),
                title=_("Not Authorized"),
            )

    @staticmethod
    def _is_system_manager():
        return "System Manager" in frappe.get_roles()

    # ------------------------------------------------------------------
    # بعد اكتمال الاعتماد: تحويل لأمر نقل أو طلب شراء
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def create_asset_movement(self):
        """Convert approved AR with spare to Asset Movement (Transfer)."""
        if not self.spare_asset:
            frappe.throw(_("No spare asset linked to create a movement"))
        if self.status != "Approved":
            frappe.throw(_("Requisition must be Approved before creating a movement"))
        doc = frappe.new_doc("Asset Movement")
        doc.purpose = "Transfer"
        doc.company = frappe.defaults.get_user_default("Company")
        doc.transaction_date = today()
        doc.append("assets", {"asset": self.spare_asset})
        doc.insert(ignore_permissions=True)
        self.db_set("status", "Fulfilled")
        return doc.name

    @frappe.whitelist()
    def create_purchase_requisition(self):
        """Create a Material Request (Purchase) — only when neither a spare
        asset nor real warehouse stock is available."""
        if self.spare_available:
            frappe.throw(_("A spare asset is available. Use 'Create Asset Movement' instead."))
        if self.stock_available:
            frappe.throw(
                _("Item is available in warehouse {0} (qty: {1}). No need to purchase.").format(
                    self.check_warehouse, self.available_qty
                )
            )
        if self.status != "Approved":
            frappe.throw(_("Requisition must be Approved before creating a purchase request."))

        mr = frappe.new_doc("Material Request")
        mr.material_request_type = "Purchase"
        mr.transaction_date = frappe.utils.today()
        mr.schedule_date = self.required_by or frappe.utils.add_days(frappe.utils.today(), 30)
        mr.custom_source_asset_requisition = self.name if frappe.db.exists("Custom Field",
            "Material Request-custom_source_asset_requisition") else None

        if self.item_code:
            mr.append("items", {
                "item_code": self.item_code,
                "qty": self.quantity or 1,
                "schedule_date": mr.schedule_date,
            })
        else:
            frappe.throw(_("Please set Item Code on the requisition before creating a purchase request."))

        mr.insert(ignore_permissions=True)
        self.db_set("material_request", mr.name)
        self.db_set("status", "Fulfilled")
        frappe.msgprint(
            f"تم إنشاء طلب الشراء: <a href='/app/material-request/{mr.name}'>{mr.name}</a>",
            alert=True, indicator="green"
        )
        return mr.name
