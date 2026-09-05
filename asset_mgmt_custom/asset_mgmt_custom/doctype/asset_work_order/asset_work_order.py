import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, now_datetime, today

from asset_mgmt_custom.overrides.asset_repair import _update_asset_maintenance_summary


class AssetWorkOrder(Document):
    FINAL_STATUSES = ("مكتمل", "ملغي", "مرفوض")
    MAINTENANCE_ROLES = ("Asset Technician", "Asset Manager", "System Manager")

    def before_insert(self):
        self._apply_sla_policy()
        if not self.assigned_technician:
            self._auto_dispatch_technician()

    def on_submit(self):
        self.db_set("status", "قيد التنفيذ")

    def on_update_after_submit(self):
        """
        الحالة (status) والحقول المرتبطة بالإتمام صارت allow_on_submit — أمر
        العمل بيتقدَّم بعد التسليم (Submit) من "قيد التنفيذ" إلى "مكتمل" عن
        طريق تعديل هذا الحقل على نفس المستند المُسلَّم، وليس عبر مستند جديد.
        عند وصوله لحالة "مكتمل" نرحِّل تكلفته الفعلية محاسبياً (مرة واحدة
        فقط) ونحدِّث إجمالي تكلفة الصيانة على الأصل.
        """
        if self.status == "مكتمل":
            self._post_maintenance_cost_gl_entry()
        _update_asset_maintenance_summary(self.asset)

    def on_cancel(self):
        self.db_set("status", "ملغي")
        self._cancel_maintenance_cost_gl_entry()
        _update_asset_maintenance_summary(self.asset)

    @frappe.whitelist()
    def complete_work_order(self):
        """
        مسار مُصرَّح به (whitelisted) وحيد لإتمام أمر العمل — يستخدمه زر
        الواجهة، وسيستخدمه لاحقاً تطبيق الموبايل بنفس الطريقة بالضبط
        (استدعاء واحد على /api/resource/Asset Work Order/<name>
        ?run_method=complete_work_order)، بدل تكرار نفس المنطق في أكثر
        من مكان. يستخدم self.save() الكامل (وليس db_set) عمداً، لأن
        on_update_after_submit (ترحيل القيد المحاسبي) لا يُنفَّذ إلا عبر
        دورة الحفظ الكاملة لمستند submitted.
        """
        self._check_maintenance_role()
        if self.docstatus != 1:
            frappe.throw(_("Work order must be submitted before it can be completed."))
        if self.status in self.FINAL_STATUSES:
            frappe.throw(
                _("This work order is already in a final status ({0}).").format(self.status)
            )
        self.status = "مكتمل"
        if not self.completion_date:
            self.completion_date = today()
        self.save()
        return self.status

    @frappe.whitelist()
    def reject_work_order(self, reason):
        """
        رفض نهائي (بدون رجوع لمقدّم الطلب) بسبب مسجَّل إجبارياً — نفس
        القرار المتَّبع في Asset Requisition.reject()، بفارق واحد: هنا
        الرفض نهائي بدون خطوة "إعادة تقديم" لاحقة، حسب ما تقرر صراحة.
        """
        self._check_maintenance_role()
        if self.docstatus != 1:
            frappe.throw(_("Work order must be submitted before it can be rejected."))
        if self.status in self.FINAL_STATUSES:
            frappe.throw(
                _("This work order is already in a final status ({0}).").format(self.status)
            )
        if not reason or not str(reason).strip():
            frappe.throw(_("Please provide a rejection reason."))

        self.status = "مرفوض"
        self.rejection_reason = reason
        self.rejected_by = frappe.session.user
        self.rejected_on = now_datetime()
        self.save()
        return self.status

    def _check_maintenance_role(self):
        """
        Branch Manager عنده write=1 على هذا الـ DocType (عشان يعدّل مسودته
        قبل التسليم)، لكن ده لازم ميدّيهوش صلاحية إتمام أو رفض طلب صيانة —
        دي مسؤولية فريق الصيانة فقط (Asset Technician/Asset Manager)،
        مش صاحب الطلب نفسه.
        """
        if not set(self.MAINTENANCE_ROLES) & set(frappe.get_roles()):
            frappe.throw(
                _("Only maintenance staff (Asset Technician / Asset Manager) can perform this action."),
                frappe.PermissionError,
            )

    def _post_maintenance_cost_gl_entry(self):
        """
        قيد محاسبي تلقائي (Idempotent) لتكلفة أمر العمل عند إتمامه:
        من حـ/ مصروف الصيانة (custom_maintenance_expense_account على فئة
        الأصل) ← إلى حـ/ التزامات صيانة مستحقة
        (custom_maintenance_accrued_liability_account) — نفس نمط OpEx
        المُستخدَم فعلياً في Asset Repair، لأن أمر العمل هنا دائماً مصروف
        تشغيلي (لا يوجد له مفهوم رسملة/CapEx مثل الإصلاح).
        """
        if self.get("journal_entry"):
            return

        total_cost = flt(self.actual_cost) or (flt(self.labor_cost) + flt(self.spare_parts_cost))
        if not total_cost:
            return

        asset = frappe.get_doc("Asset", self.asset)
        company = asset.company or frappe.defaults.get_user_default("Company")

        category_account = frappe.db.get_value(
            "Asset Category Account",
            {"parent": asset.asset_category, "company_name": company},
            ["custom_maintenance_expense_account", "custom_maintenance_accrued_liability_account"],
            as_dict=True,
        )
        if not category_account or not category_account.custom_maintenance_expense_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Expense Account' on the Asset Category Account "
                    "for {0} / {1} before completing this work order."
                ).format(asset.asset_category, company),
                title=_("Missing Maintenance Expense Account"),
            )
        if not category_account.custom_maintenance_accrued_liability_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Accrued Liability Account' on the Asset Category "
                    "Account for {0} / {1} before completing this work order."
                ).format(asset.asset_category, company),
                title=_("Missing Accrued Liability Account"),
            )

        # مركز التكلفة: أولوية للحقل المُدخَل يدوياً على أمر العمل نفسه، وإلا
        # مركز تكلفة الفرع (custom_cost_center) المرتبط بأصل هذا الأمر، وإلا
        # مركز تكلفة الأصل نفسه — بدل ما يفشل القيد بدون مركز تكلفة.
        cost_center = (
            self.cost_center
            or (self.branch and frappe.db.get_value("Branch", self.branch, "custom_cost_center"))
            or asset.get("cost_center")
        )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.completion_date or today()
        je.company = company
        if cost_center:
            je.cost_center = cost_center
        je.user_remark = _("Maintenance work order cost for Asset {0} via {1}").format(
            asset.asset_name, self.name
        )

        je.append("accounts", {
            "account": category_account.custom_maintenance_expense_account,
            "debit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })
        je.append("accounts", {
            "account": category_account.custom_maintenance_accrued_liability_account,
            "credit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": self.asset,
        })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("journal_entry", je.name, update_modified=False)

    def _cancel_maintenance_cost_gl_entry(self):
        je_name = self.get("journal_entry")
        if not je_name or not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.cancel()

    def _apply_sla_policy(self):
        """
        تُحدَّد مواعيد الاستجابة/الحل المستحقة مرة واحدة عند الإنشاء بناءً
        على سياسة SLA المطابقة لأولوية أمر العمل، بدل الثوابت الثابتة
        (48 ساعة/3 أيام) التي كانت مكتوبة مباشرة في الكود سابقاً.
        """
        if not self.priority:
            return

        policy = frappe.db.get_value(
            "Asset Maintenance SLA Policy",
            self.priority,
            ["name", "response_hours", "resolution_hours"],
            as_dict=True,
        )
        if not policy:
            return

        base = now_datetime()
        self.sla_policy = policy.name
        self.response_due_by = add_to_date(base, hours=flt(policy.response_hours))
        self.resolution_due_by = add_to_date(base, hours=flt(policy.resolution_hours))

    def _auto_dispatch_technician(self):
        """
        توزيع تلقائي لأمر العمل على الفني الأقل تحميلاً حالياً من بين
        الفنيين المؤهلين (المسجَّلين ضمن Asset Maintenance Team بنفس شركة
        الأصل، وتخصصهم (custom_skill_category) يطابق فئة الأصل أو عام بلا
        تخصص محدد) — بدل ترك أمر العمل بلا فني مُكلَّف دائماً حتى يُسند
        يدوياً. لا يفعل شيئاً إذا لم يوجد أي فني مؤهل متاح (تحت الحد
        الأقصى للتحميل المتزامن)، فيبقى التكليف اليدوي كما كان.
        """
        if not self.asset:
            return

        asset_info = frappe.db.get_value("Asset", self.asset, ["asset_category", "company"], as_dict=True)
        if not asset_info:
            return

        candidates = frappe.db.sql("""
            SELECT mtm.team_member AS technician, mtm.custom_max_concurrent_orders AS max_orders
            FROM `tabMaintenance Team Member` mtm
            JOIN `tabAsset Maintenance Team` amt ON amt.name = mtm.parent
            WHERE amt.company = %(company)s
              AND (
                  IFNULL(mtm.custom_skill_category, '') = ''
                  OR mtm.custom_skill_category = %(category)s
              )
        """, {"company": asset_info.company, "category": asset_info.asset_category}, as_dict=True)
        if not candidates:
            return

        best_technician = None
        best_load = None
        for candidate in candidates:
            load = frappe.db.count("Asset Work Order", {
                "assigned_technician": candidate.technician,
                "status": ["in", ["مفتوح", "قيد التنفيذ"]],
                "docstatus": ["<", 2],
            })
            cap = candidate.max_orders or 0
            if cap and load >= cap:
                continue
            if best_load is None or load < best_load:
                best_technician = candidate.technician
                best_load = load

        if best_technician:
            self.assigned_technician = best_technician
