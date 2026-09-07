import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, now_datetime, today

from asset_mgmt_custom.overrides.asset_repair import _update_asset_maintenance_summary
from asset_mgmt_custom.notifications import send_critical_alert
from asset_mgmt_custom.utils.notify import notify_user


PRIORITY_RANK = {"عادي": 1, "متوسط": 2, "عاجل": 3, "حرج": 4}

# مصفوفة الحرجية (Asset Criticality Matrix) كانت DocType موجوداً بالفعل
# (بيانات تقييم فقط: مستوى الحرجية، الأثر، احتمالية العطل...) لكن غير
# مربوط بأي قرار تشغيلي فعلي — مجرد تقرير يُقرأ يدوياً. هذا هو أدنى حد
# لأولوية أمر العمل حسب حرجية الأصل، بحيث لا يُفتح أمر عمل لأصل "حرج
# جداً" بأولوية "عادي" لمجرد أن مُنشئ الطلب لم ينتبه لذلك.
CRITICALITY_PRIORITY_FLOOR = {
    "Critical": "حرج",
    "High": "عاجل",
}


class AssetWorkOrder(Document):
    FINAL_STATUSES = ("مكتمل", "ملغي", "مرفوض")
    MAINTENANCE_ROLES = ("Asset Technician", "Asset Manager", "System Manager", "Maintenance Vendor")
    UNRESTRICTED_ROLES = ("Asset Technician", "Asset Manager", "System Manager")
    BRANCH_CONFIRMATION_ROLES = ("Asset Manager", "System Manager", "Branch Manager")

    def validate(self):
        self._set_default_title()
        self._apply_criticality_priority_floor()
        self._validate_capitalized_overhaul_requires_asset()
        self._validate_general_complaint_department()

    def _validate_general_complaint_department(self):
        """
        الجهة المعنية (complaint_department) إجبارية فقط لشكوى عامة بلا
        أصل — أمر عمل مرتبط بأصل يُوجَّه أصلاً عبر فئة الأصل نفسها، فلا
        داعي لملء هذا الحقل. reqd في الـ JSON مشروط بنفس الفحص من جهة
        الواجهة (mandatory_depends_on)، وهذا الفحص هو الحارس الفعلي على
        مستوى الخادم لأي استدعاء API مباشر يتجاوز الواجهة.
        """
        if not self.asset and not self.complaint_department:
            frappe.throw(
                _("Please select which department this general complaint (not linked to an asset) "
                  "should go to: IT or General Maintenance."),
                title=_("Department Required"),
            )
        if self.asset:
            self.complaint_department = None

    def _validate_capitalized_overhaul_requires_asset(self):
        """
        شكوى عامة (بلا أصل مرتبط) لا يمكن أن تُرسمَل كعمرة كبرى — الرسملة
        بحكم تعريفها ترفع القيمة الدفترية وتمدد العمر الإنتاجي لأصل بعينه
        (انظر _escalate_to_asset_repair)، وهو غير موجود هنا أصلاً.
        """
        if not self.asset and self.cost_classification == "Capitalized Overhaul":
            frappe.throw(
                _("'Capitalized Overhaul' cost classification requires a linked Asset — "
                  "this work order has none (general complaint)."),
                title=_("Asset Required"),
            )

    def _apply_criticality_priority_floor(self):
        """
        يرفع أولوية أمر العمل تلقائياً (لا يخفضها أبداً) إذا كان الأصل
        مُصنَّفاً High/Critical في Asset Criticality Matrix وأولوية
        الطلب الحالية أقل من الحد الأدنى المفروض لهذا التصنيف.
        """
        if not self.asset:
            return
        floor = CRITICALITY_PRIORITY_FLOOR.get(
            frappe.db.get_value("Asset Criticality Matrix", {"asset": self.asset}, "criticality_level")
        )
        if not floor:
            return
        if PRIORITY_RANK.get(self.priority, 0) < PRIORITY_RANK[floor]:
            self.priority = floor

    def before_submit(self):
        self._enforce_loto_gate()

    def _enforce_loto_gate(self):
        """
        تسليم أمر العمل (submit) هو اللحظة التي تتحول فيها حالته تلقائياً
        إلى "قيد التنفيذ" (on_submit) — أي بدء العمل الفعلي على الأصل.
        لو مرتبط بتصريح عمل (work_permit) يتطلب عزل طاقة (requires_loto)،
        يُمنَع التسليم حتى يُوقَّع اكتمال قائمة العزل فعلياً
        (Asset Work Permit.complete_loto_checklist) — لا يمكن بدء العمل
        على معدة خطرة بدون توثيق العزل أولاً.
        """
        if not self.get("work_permit"):
            return
        permit = frappe.db.get_value(
            "Asset Work Permit", self.work_permit, ["requires_loto", "loto_verified"], as_dict=True
        )
        if permit and permit.requires_loto and not permit.loto_verified:
            frappe.throw(
                _(
                    "The linked Work Permit {0} requires energy isolation (LOTO) sign-off before "
                    "this work order can start. Complete and sign off the isolation checklist on "
                    "the permit first."
                ).format(self.work_permit),
                title=_("LOTO Sign-off Required"),
            )

    def before_insert(self):
        self._apply_sla_policy()
        if not self.assigned_technician:
            self._auto_dispatch_technician()

    def after_insert(self):
        if self.priority == "حرج":
            if self.asset:
                subject_line = _("عطل حرج: {0}").format(self.title)
                message = _("أمر عمل بأولوية 'حرج' على الأصل {0} ({1}). الوصف: {2}").format(
                    self.asset, frappe.db.get_value("Asset", self.asset, "asset_name") or "",
                    (self.problem_description or "")[:200],
                )
            else:
                subject_line = _("شكوى عامة حرجة: {0}").format(self.title)
                message = _("شكوى عامة بأولوية 'حرج' غير مرتبطة بأصل محدد. الوصف: {0}").format(
                    (self.problem_description or "")[:200],
                )
            send_critical_alert(
                subject=subject_line,
                message=message,
                reference_doctype="Asset Work Order",
                reference_name=self.name,
            )
        if self.assigned_technician:
            notify_user(
                self.assigned_technician,
                _("تم تكليفك بأمر عمل جديد: {0}").format(self.title),
                reference_doctype="Asset Work Order",
                reference_name=self.name,
            )

    def _set_default_title(self):
        """
        title لم يعد إجبارياً (problem_description أصبح هو الإجباري بدلاً
        منه) — لتبسيط نموذج الإدخال السريع (Quick Entry) لطلب صيانة عاجل:
        اسم الأصل + وصف المشكلة كافيان لفتح الطلب، بدون إجبار كتابة عنوان
        منفصل. لو تُرك title فارغاً، يُولَّد تلقائياً من الاثنين معاً.
        """
        if self.title:
            return

        asset_label = frappe.db.get_value("Asset", self.asset, "asset_name") if self.asset else None
        desc = (self.problem_description or "").strip().replace("\n", " ")
        if len(desc) > 60:
            desc = desc[:57] + "..."

        if asset_label and desc:
            self.title = f"{asset_label} — {desc}"
        elif asset_label:
            self.title = asset_label
        else:
            self.title = _("طلب صيانة جديد")

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
        if self.asset:
            _update_asset_maintenance_summary(self.asset)

    def on_cancel(self):
        self.db_set("status", "ملغي")
        self._cancel_maintenance_cost_gl_entry()
        self._cancel_linked_spare_part_requests()
        self._cancel_linked_asset_repair()
        if self.asset:
            _update_asset_maintenance_summary(self.asset)

    def _cancel_linked_asset_repair(self):
        repair_name = self.get("asset_repair")
        if not repair_name or not frappe.db.exists("Asset Repair", repair_name):
            return
        repair = frappe.get_doc("Asset Repair", repair_name)
        if repair.docstatus == 1:
            repair.cancel()

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
        self._auto_issue_linked_spare_parts()
        self.status = "مكتمل"
        if not self.completion_date:
            self.completion_date = today()
        if self.get("cost_classification") == "Capitalized Overhaul":
            self._escalate_to_asset_repair()
        self.save()
        if self.requested_by:
            notify_user(
                self.requested_by,
                _("اكتمل طلب الصيانة {0} — يمكنك تأكيد حل المشكلة الآن.").format(self.title),
                reference_doctype="Asset Work Order",
                reference_name=self.name,
            )
        return self.status

    def _escalate_to_asset_repair(self):
        """
        عمرة كبرى/استبدال جزء جوهري: أمر العمل نفسه دائماً مصروف تشغيلي
        (انظر تعليق _post_maintenance_cost_gl_entry)، فمحاسبة الرسملة
        الفعلية (رفع القيمة الدفترية، تمديد العمر الإنتاجي، القيد
        المحاسبي الصحيح CapEx) موجودة بالفعل وبشكل كامل وصحيح في Asset
        Repair (انظر overrides/asset_repair.py) — بما فيها فرض إدخال
        increase_in_asset_life قبل الإتمام، والتوجيه المحاسبي الصحيح إلى
        Capital Maintenance WIP Account. بدل تكرار كل هذا المنطق هنا من
        جديد (ومخاطرة تصادمه مع نسخة Asset Repair)، نُنشئ سجل Asset
        Repair حقيقياً من بيانات أمر العمل ونُسلِّمه، فيتكفل هو بكل شيء.
        """
        if self.get("asset_repair"):
            return
        if not self.get("increase_in_asset_life_months"):
            frappe.throw(
                _("Please enter 'Increase In Asset Life (Months)' before completing a "
                  "Capitalized Overhaul work order — otherwise the cost is capitalized but "
                  "the asset's useful life and depreciation schedule are never extended."),
                title=_("Missing Life Extension"),
            )

        asset = frappe.get_doc("Asset", self.asset)
        total_cost = flt(self.actual_cost) or (flt(self.labor_cost) + flt(self.spare_parts_cost))

        technician_name = None
        if self.assigned_technician:
            technician_name = frappe.db.get_value("User", self.assigned_technician, "full_name")

        repair = frappe.new_doc("Asset Repair")
        repair.asset = self.asset
        repair.company = asset.company
        repair.failure_date = self.creation
        repair.completion_date = self.completion_date or today()
        repair.repair_status = "Completed"
        repair.description = self.problem_description
        repair.custom_technician_name = technician_name or self.assigned_technician
        repair.custom_repair_notes = self.completion_notes or self.problem_description
        repair.repair_cost = total_cost
        repair.capitalize_repair_cost = 1
        repair.increase_in_asset_life = self.increase_in_asset_life_months
        repair.cost_center = self.cost_center or asset.get("cost_center")
        repair.insert(ignore_permissions=True)
        repair.submit()

        self.asset_repair = repair.name

    def _auto_issue_linked_spare_parts(self):
        """
        قبل الفصل: تكلفة قطع الغيار (spare_parts_cost) كانت رقماً يُكتب
        يدوياً، بدون أي أثر مخزني فعلي — مجرد رقم يُستخدم في القيد
        المحاسبي. الآن: أي Asset Spare Part Request مرتبط بهذا الأمر
        (asset_work_order) وبحالة "Approved" لم يُصرَف بعد، يُصرَف تلقائياً
        هنا (حركة Stock Entry حقيقية عبر issue_spare_part() الموجودة
        أصلاً — بلا تكرار منطق)، ثم يُجمَّع spare_parts_cost من القيمة
        المُقيَّمة الفعلية لهذه الحركات (وليس تقديراً يدوياً بعد الآن).

        هذا يعني أيضاً أن تكلفة قطع الغيار لم تعد تُرحَّل ضمن القيد
        اليومي في _post_maintenance_cost_gl_entry — لأن Stock Entry نفسها
        تُنشئ قيدها المحاسبي الخاص بها تلقائياً (مدين حساب مصروف الصيانة/
        دائن قيمة المخزون بالمستودع) لحظة تسليمها؛ ترحيلها مرة أخرى ضمن
        قيد أمر العمل كان سيُكرِّر نفس المصروف محاسبياً مرتين.
        """
        requests = frappe.get_all(
            "Asset Spare Part Request",
            filters={"asset_work_order": self.name, "status": "Approved", "docstatus": 1},
            pluck="name",
        )
        if not requests:
            return

        total = flt(self.spare_parts_cost)
        for request_name in requests:
            request = frappe.get_doc("Asset Spare Part Request", request_name)
            se_name = request.issue_spare_part()
            total += flt(frappe.db.get_value("Stock Entry", se_name, "total_outgoing_value"))

        self.spare_parts_cost = total

    def _cancel_linked_spare_part_requests(self):
        """
        عكس تلقائي عند إلغاء أمر العمل: أي طلب قطعة غيار صُرف فعلياً عبر
        هذا الأمر (stock_entry موجود) يُلغى بالكامل — يُلغي حركة المخزون
        الخاصة به ويُعيد الكمية إلى Asset Spare Part، عبر
        Asset Spare Part Request.on_cancel() الموجودة أصلاً (بلا تكرار).

        الإلغاء قد يفشل فعلياً (ليس افتراضياً نظرياً): لو حدثت حركة لاحقة
        على نفس المستودع بعد الصرف (تسوية مخزون Stock Reconciliation، أو
        صرف/بيع آخر)، سيرفض core إلغاء الـ Stock Entry القديمة لمنع هبوط
        الرصيد لقيمة سالبة بتاريخ ماضٍ. بدون معالجة، هذا الاستثناء كان
        سيُسقِط عملية إلغاء أمر العمل بالكامل (on_cancel لا يكتمل، فيبقى
        أمر العمل غير قابل للإلغاء نهائياً حتى تُحل المشكلة يدوياً في
        المخزون أولاً) — بدلاً من ذلك: نُسجِّل الفشل وننبِّه الإدارة
        المالية لتسوية يدوية، ونكمل إلغاء بقية الطلبات وأمر العمل نفسه.
        """
        requests = frappe.get_all(
            "Asset Spare Part Request",
            filters={"asset_work_order": self.name, "docstatus": 1},
            pluck="name",
        )
        for request_name in requests:
            request = frappe.get_doc("Asset Spare Part Request", request_name)
            if not request.get("stock_entry"):
                continue
            try:
                request.cancel()
            except Exception:
                frappe.log_error(
                    title="Failed to auto-cancel Asset Spare Part Request on Work Order cancellation",
                    message=frappe.get_traceback(),
                )
                send_critical_alert(
                    _("Manual stock reversal required — {0}").format(request_name),
                    _(
                        "Cancelling Asset Work Order {0} could not automatically reverse the linked "
                        "Stock Entry for Asset Spare Part Request {1} (likely a later stock movement "
                        "on the same warehouse blocks it). Please reverse it manually in Stock."
                    ).format(self.name, request_name),
                    reference_doctype="Asset Spare Part Request",
                    reference_name=request_name,
                )

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
        if self.requested_by:
            notify_user(
                self.requested_by,
                _("تم رفض طلب الصيانة {0}: {1}").format(self.title, reason),
                reference_doctype="Asset Work Order",
                reference_name=self.name,
            )
        return self.status

    @frappe.whitelist()
    def confirm_branch_resolution(self, confirmed_working, rating=None, feedback=None):
        """
        تأكيد الفرع (وليس الفني) أن الجهاز يعمل فعلاً — منفصل عمداً عن
        "مكتمل" التي يضعها الفني بمجرد انتهائه من العمل، ولا تعني بالضرورة
        أن نتيجة الصيانة صحيحة فعلياً من وجهة نظر من طلبها. لا يُعاد فتح
        هذا الأمر عند استمرار المشكلة (كان سيُعرِّض قيده المحاسبي/حركاته
        المخزنية المُرحَّلة بالفعل للتناقض) — بدلاً من ذلك يُنشأ أمر متابعة
        جديد تلقائياً، بنفس أسلوب التصعيد المُتَّبع فعلياً في هذا التطبيق
        (Asset Complaint.escalate_to_work_order، Asset Environmental Log).
        """
        if self.status != "مكتمل":
            frappe.throw(_("Only a completed work order can be confirmed by the branch."))
        if self.branch_confirmation_status:
            frappe.throw(_("This work order has already been confirmed by the branch."))
        self._check_branch_confirmation_role()

        confirmed_working = cint(confirmed_working)
        if rating is not None:
            rating = cint(rating)
            if rating < 1 or rating > 5:
                frappe.throw(_("Rating must be between 1 and 5."))
            self.branch_rating = rating
        if feedback:
            self.branch_feedback = feedback

        self.branch_confirmation_status = "Confirmed Working" if confirmed_working else "Issue Persists"
        self.branch_confirmed_by = frappe.session.user
        self.branch_confirmed_on = now_datetime()

        if not confirmed_working:
            self.follow_up_work_order = self._create_follow_up_work_order()
            if self.assigned_technician:
                notify_user(
                    self.assigned_technician,
                    _("الفرع أكَّد استمرار المشكلة في {0} — أُنشئ أمر متابعة {1}.").format(
                        self.title, self.follow_up_work_order
                    ),
                    reference_doctype="Asset Work Order",
                    reference_name=self.follow_up_work_order,
                )

        self.save()
        return {
            "name": self.name,
            "branch_confirmation_status": self.branch_confirmation_status,
            "follow_up_work_order": self.follow_up_work_order,
        }

    def _check_branch_confirmation_role(self):
        if self.requested_by == frappe.session.user:
            return
        roles = set(frappe.get_roles())
        if roles & set(self.BRANCH_CONFIRMATION_ROLES):
            return
        frappe.throw(
            _("Only the requester of this work order, or a branch/asset manager, can confirm its resolution."),
            frappe.PermissionError,
        )

    def _create_follow_up_work_order(self):
        follow_up = frappe.new_doc("Asset Work Order")
        follow_up.asset = self.asset
        follow_up.branch = self.branch
        follow_up.work_type = self.work_type
        follow_up.priority = self.priority
        follow_up.problem_description = _(
            "إعادة فتح — لم يُؤكَّد حل المشكلة بعد أمر العمل السابق {0}:\n{1}"
        ).format(self.name, self.problem_description or "")
        follow_up.requested_by = frappe.session.user
        follow_up.insert(ignore_permissions=True)
        follow_up.submit()
        return follow_up.name

    def _check_maintenance_role(self):
        """
        Branch Manager عنده write=1 على هذا الـ DocType (عشان يعدّل مسودته
        قبل التسليم)، لكن ده لازم ميدّيهوش صلاحية إتمام أو رفض طلب صيانة —
        دي مسؤولية فريق الصيانة فقط (Asset Technician/Asset Manager) أو
        مورد صيانة خارجي (Maintenance Vendor) مُسنَد إليه الأمر تحديداً،
        مش صاحب الطلب نفسه.

        دفاع مزدوج عمداً: has_permission()/get_permission_query_conditions
        أسفل هذا الملف يمنعان أصلاً مورد الصيانة من فتح أمر عمل غير مُسنَد
        له عبر أي مسار (واجهة، API، REST) — هذا الفحص هنا طبقة حماية
        إضافية داخل الطريقة نفسها، تحسباً لأي مسار نداء مباشر يتجاوز طبقة
        الصلاحيات القياسية (مثلاً استدعاء من سكريبت سيرفر آخر).
        """
        roles = set(frappe.get_roles())
        if roles & set(self.UNRESTRICTED_ROLES):
            return
        if "Maintenance Vendor" in roles and self.assigned_technician == frappe.session.user:
            return
        frappe.throw(
            _("Only maintenance staff, or the vendor assigned to this specific work order, "
              "can perform this action."),
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

        ملاحظة مهمة: spare_parts_cost لم يعد يُضاف هنا إلى القيد — منذ
        _auto_issue_linked_spare_parts()، أصبحت تكلفة قطع الغيار (إن
        وُجدت طلبات قطع غيار مرتبطة بهذا الأمر) تُرحَّل محاسبياً من خلال
        القيد التلقائي الخاص بـ Stock Entry نفسها (تُنشئه ERPNext تلقائياً
        عند تسليم حركة Material Issue). لو تُرحِّل هنا مرة أخرى ضمن
        total_cost، ستُحمَّل نفس تكلفة قطع الغيار على حساب مصروف الصيانة
        مرتين. لذلك: total_cost = العمالة (labor_cost) فقط، إلا لو حُدِّد
        actual_cost يدوياً كتجاوز صريح — وفي هذه الحالة مسؤولية من يُدخله
        عدم تضمين تكلفة قطع غيار مصروفة فعلياً بالفعل عبر Stock Entry.

        ولا تُنشئ هذه الدالة أي قيد إطلاقاً لو صُنِّف الأمر "Capitalized
        Overhaul" (أي asset_repair مضبوط) — عندها Asset Repair المرتبط
        هو من يتكفل بمحاسبة الرسملة الكاملة (انظر _escalate_to_asset_repair).
        """
        if self.get("asset_repair"):
            return
        if self.get("journal_entry"):
            return
        if not self.asset:
            # شكوى عامة بلا أصل مرتبط: لا يوجد Asset Category Account لتحديد
            # حسابات المصروف/الالتزام منه، فلا يمكن ترحيل قيد محاسبي تلقائي —
            # تكلفتها (إن أُدخلت) تبقى رقماً مرجعياً على أمر العمل نفسه فقط.
            return

        total_cost = flt(self.actual_cost) or flt(self.labor_cost)
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
        الفنيين المؤهلين — بدل ترك أمر العمل بلا فني مُكلَّف دائماً حتى
        يُسند يدوياً. لا يفعل شيئاً إذا لم يوجد أي فني مؤهل متاح (تحت الحد
        الأقصى للتحميل المتزامن)، فيبقى التكليف اليدوي كما كان.

        مسار أمر عمل مرتبط بأصل: الفنيون ضمن Asset Maintenance Team بنفس
        شركة الأصل، وتخصصهم (custom_skill_category) يطابق فئة الأصل أو
        عام بلا تخصص محدد.

        مسار شكوى عامة (بلا أصل): لا توجد فئة أصل لمطابقتها، فنستخدم
        complaint_department بدلاً منها — فقط الفنيون الذين حدَّدوا صراحة
        هذه الجهة عبر custom_complaint_department (اختيار صريح، وليس
        "فارغ = عام" كما في التخصص بالأصل، حتى لا يُسنَد لفني تخصصه صيانة
        أجهزة مثلاً بلاغ تقنية معلومات لمجرد ترك الحقل فارغاً).
        """
        if self.asset:
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
        else:
            if not self.complaint_department:
                return
            company = frappe.defaults.get_global_default("company")
            if not company:
                return
            candidates = frappe.db.sql("""
                SELECT mtm.team_member AS technician, mtm.custom_max_concurrent_orders AS max_orders
                FROM `tabMaintenance Team Member` mtm
                JOIN `tabAsset Maintenance Team` amt ON amt.name = mtm.parent
                WHERE amt.company = %(company)s
                  AND mtm.custom_complaint_department = %(department)s
            """, {"company": company, "department": self.complaint_department}, as_dict=True)
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


# ---------------------------------------------------------------------------
# Maintenance Vendor scoping — bوابة موردي الصيانة الخارجيين
# ---------------------------------------------------------------------------
# مورد صيانة خارجي (Maintenance Vendor) لازم ميشوفش إلا أوامر العمل
# المُسنَدة له تحديداً (assigned_technician = مستخدمه)، بلا صلاحية كاملة
# زي Asset Manager. لا يوجد حقل Link مباشر يصلح لتقييد User Permission
# التلقائي هنا (assigned_technician هو نفسه حقل Link->User، وتقييده عبر
# User Permission كان سيُخفي كل المستخدمين الآخرين من كل الحقول في
# النظام لهذا المستخدم) — لذلك يُستخدَم نفس أسلوب Frappe القياسي لتقييد
# "مُسنَد إليّ فقط" (has_permission + permission_query_conditions)، مسجَّلان
# في hooks.py.

def get_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & set(AssetWorkOrder.UNRESTRICTED_ROLES):
        return ""
    if "Maintenance Vendor" in roles:
        return f"`tabAsset Work Order`.assigned_technician = {frappe.db.escape(user)}"
    return ""


def has_permission(doc, ptype=None, user=None):
    if not user:
        user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & set(AssetWorkOrder.UNRESTRICTED_ROLES):
        return None
    if "Maintenance Vendor" in roles:
        return doc.assigned_technician == user
    return None
