"""
Asset Repair override
---------------------
Validate:
  - عند اكتمال الإصلاح (Completed): يُشترط اسم الفني + ملاحظات الإصلاح + تاريخ الاكتمال
  - CapEx/OpEx: إذا كان إصلاح ضمان، تُصفَّر التكاليف
  - CapEx/OpEx: إذا تجاوزت التكلفة حد الرسملة في Asset Category، يُفعَّل capitalize_repair_cost
  - CapEx: عند اكتمال إصلاح مُرسمَل (capitalize_repair_cost)، يُشترط إدخال عدد الشهور
    الإضافية للعمر الإنتاجي (increase_in_asset_life) — بدونها ERPNext يرسمل التكلفة
    لكن لا يمدد العمر ولا يعيد جدولة الإهلاك

On Submit:
  - يُحدِّث إجمالي تكلفة الصيانة (custom_total_maintenance_cost) على الأصل
  - يُحدِّث تاريخ آخر صيانة (custom_last_maintenance_date) على الأصل
  - يُسجِّل ملخص الإصلاح في Asset Activity
  - قيد محاسبي تلقائي لتكلفة الإصلاح (فقط عند عدم ربط فاتورة شراء — لو فيه فاتورة،
    ERPNext الأساسي أو محاسبة الفاتورة نفسها بيتكفلوا بالقيد فعلاً، وأي قيد إضافي
    هنا هيكرر المبلغ):
      * CapEx (capitalize_repair_cost): من حـ/ الأصل ← إلى حـ/ وساطة "أصول تحت
        الصيانة الرأسمالية" (custom_capital_maintenance_wip_account على فئة
        الأصل) — بدل الترحيل المباشر لحساب الأصل.
      * OpEx: من حـ/ مصروف الصيانة (custom_maintenance_expense_account) ←
        إلى حـ/ التزامات صيانة مستحقة (custom_maintenance_accrued_liability_account
        على فئة الأصل) — وليس حساب موردين الشركة العام، لأن ERPNext يشترط
        تحديد طرف (Party) لأي قيد على حساب Payable، وإصلاح بدون فاتورة
        شراء ليس له مورد محدد أصلاً.

On Cancel:
  - يُعيد حساب إجمالي التكلفة وتاريخ آخر صيانة بعد حذف هذا السند
  - يُلغي قيد اليومية المُنشأ (لو موجود)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, time_diff_in_hours, today


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate(doc, method=None):
    if doc.repair_status == "Completed":
        _validate_completion_requirements(doc)
    _auto_classify_capex(doc)
    _calculate_downtime(doc)
    if doc.repair_status == "Completed":
        _require_life_extension_when_capitalized(doc)


def _calculate_downtime(doc):
    if doc.get("custom_downtime_start") and doc.get("custom_downtime_end"):
        hours = time_diff_in_hours(doc.custom_downtime_end, doc.custom_downtime_start)
        doc.custom_downtime_hours = round(max(hours, 0), 2)
    else:
        doc.custom_downtime_hours = 0


def _validate_completion_requirements(doc):
    """تحقق من اكتمال بيانات التوثيق قبل إغلاق طلب الإصلاح."""
    errors = []

    if not doc.get("custom_technician_name"):
        errors.append(_("Technician Name is required when marking repair as Completed."))

    if not doc.get("custom_repair_notes"):
        errors.append(_("Repair Notes (detailed description) is required when marking repair as Completed."))

    if not doc.completion_date:
        errors.append(_("Completion Date is required when marking repair as Completed."))

    if errors:
        frappe.throw(
            "<br>".join(errors),
            title=_("Repair Documentation Incomplete"),
        )


def _auto_classify_capex(doc):
    """If warranty repair, zero out costs. If cost > threshold, auto-set capitalize.

    Asset Repair has no 'asset_category' field of its own (unlike Asset) —
    it must always be looked up via the linked Asset. A previous version of
    this function read/wrote doc.asset_category directly, which crashed with
    AttributeError on every single Asset Repair the first time this ran,
    since Python raises on reading an attribute that was never set for a
    field the doctype doesn't declare."""
    if doc.get("custom_is_warranty_repair"):
        doc.capitalize_repair_cost = 0
        return

    asset_category = frappe.db.get_value("Asset", doc.asset, "asset_category")

    threshold = 0
    if asset_category:
        threshold = frappe.db.get_value(
            "Asset Category", asset_category, "custom_capitalization_threshold"
        ) or 0

    total = flt(doc.repair_cost) + flt(doc.get("custom_labor_cost"))
    if threshold and total > flt(threshold):
        doc.capitalize_repair_cost = 1


def _require_life_extension_when_capitalized(doc):
    """
    ERPNext رسملة (capitalize_repair_cost) بدون increase_in_asset_life تُضيف
    التكلفة لقيمة الأصل لكن لا تمدد العمر الإنتاجي ولا تعيد جدولة الإهلاك —
    وده غالباً غلط محاسبي غير مقصود. نجبر إدخال القيمة قبل اكتمال أي إصلاح مُرسمَل.
    """
    if not doc.get("capitalize_repair_cost"):
        return
    if not doc.get("increase_in_asset_life"):
        frappe.throw(
            _(
                "Please enter 'Increase In Asset Life (Months)' before completing a "
                "capitalized (CapEx) repair — otherwise the cost is capitalized but the "
                "asset's useful life and depreciation schedule are never extended."
            ),
            title=_("Missing Life Extension"),
        )


# ---------------------------------------------------------------------------
# On Submit
# ---------------------------------------------------------------------------

def on_submit(doc, method=None):
    _update_asset_maintenance_summary(doc.asset)
    _log_repair_activity(doc)
    _post_repair_cost_gl_entry(doc)


def _update_asset_maintenance_summary(asset_name):
    """
    يُعيد حساب على مستوى الأصل نفسه (وليس على مستوى مستند واحد)، مجمِّعاً
    التكلفة من كل مصادر الصيانة الموجودة فعلياً في هذا التطبيق معاً — Asset
    Repair وAsset Work Order — حتى يعكس custom_total_maintenance_cost
    التكلفة الكاملة عبر عمر الأصل، بغض النظر عن أي مستند صدرت منه:
    - إجمالي تكلفة جميع الإصلاحات وأوامر العمل المكتملة على الأصل
    - تاريخ آخر صيانة مكتملة (من أي من المصدرين)
    """
    totals = frappe.db.sql(
        """
        SELECT
            SUM(cost) AS total_cost,
            MAX(last_date) AS last_date,
            SUM(downtime) AS total_downtime
        FROM (
            SELECT
                (total_repair_cost + IFNULL(custom_labor_cost, 0)) AS cost,
                CASE WHEN repair_status = 'Completed' THEN DATE(completion_date) END AS last_date,
                IFNULL(custom_downtime_hours, 0) AS downtime
            FROM `tabAsset Repair`
            WHERE asset = %(asset)s AND docstatus = 1

            UNION ALL

            SELECT
                IFNULL(actual_cost, 0) AS cost,
                CASE WHEN status = 'مكتمل' THEN completion_date END AS last_date,
                0 AS downtime
            FROM `tabAsset Work Order`
            WHERE asset = %(asset)s AND docstatus = 1
        ) combined
        """,
        {"asset": asset_name},
        as_dict=True,
    )

    total_cost = flt(totals[0].total_cost) if totals else 0.0
    last_date = totals[0].last_date if totals else None
    total_downtime = flt(totals[0].total_downtime) if totals else 0.0

    frappe.db.set_value(
        "Asset",
        asset_name,
        {
            "custom_total_maintenance_cost": total_cost,
            "custom_last_maintenance_date": last_date,
            "custom_total_downtime_hours": total_downtime,
        },
        update_modified=False,
    )


def _post_repair_cost_gl_entry(doc):
    """
    ERPNext's own GL posting for repair cost only fires for capitalized
    (CapEx) repairs, and only when a Purchase Invoice is linked (it reads
    the PI's own expense account). Plain OpEx repairs get NO automatic GL
    entry at all — even with a PI linked, since the PI's own accounting
    already books the expense on its own submission.

    We only need to step in when there's no PI: with one linked, either
    ERPNext's native path (CapEx) or the PI's own posting (OpEx) already
    handles it correctly, and adding our own entry here would double-book
    the cost.
    """
    if doc.get("purchase_invoice"):
        return
    if doc.get("custom_journal_entry"):
        return

    total_cost = flt(doc.repair_cost) + flt(doc.get("custom_labor_cost"))
    if not total_cost:
        return

    asset = frappe.get_doc("Asset", doc.asset)
    company = asset.company or frappe.defaults.get_user_default("Company")

    category_account = frappe.db.get_value(
        "Asset Category Account",
        {"parent": asset.asset_category, "company_name": company},
        [
            "fixed_asset_account",
            "custom_capital_maintenance_wip_account",
            "custom_maintenance_expense_account",
            "custom_maintenance_accrued_liability_account",
        ],
        as_dict=True,
    )
    if not category_account:
        frappe.throw(
            _("No Asset Category Account is set up for category {0} / company {1}.").format(
                asset.asset_category, company
            ),
            title=_("Missing Account Setup"),
        )

    # حقل cost_center على Asset Repair نفسه اختياري — لو فاضي، نرجع لمركز
    # تكلفة الأصل نفسه بدل ما نسيب القيد من غير مركز تكلفة، لأن ERPNext
    # يشترط مركز تكلفة (سطراً أو على مستوى القيد) على أي حساب أرباح وخسائر
    # (مصروف/إيراد) — مصروف الصيانة هنا حساب من هذا النوع.
    cost_center = doc.cost_center or asset.cost_center

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = doc.completion_date or today()
    je.company = company
    if cost_center:
        je.cost_center = cost_center

    if doc.get("capitalize_repair_cost"):
        wip_account = category_account.custom_capital_maintenance_wip_account
        if not wip_account:
            frappe.throw(
                _(
                    "Please set 'Capital Maintenance WIP Account' on the Asset Category "
                    "Account for {0} / {1} before completing a capitalized repair without "
                    "a linked Purchase Invoice."
                ).format(asset.asset_category, company),
                title=_("Missing WIP Account"),
            )
        je.user_remark = _("Capitalized repair cost for Asset {0} via {1}").format(
            asset.asset_name, doc.name
        )
        je.append("accounts", {
            "account": category_account.fixed_asset_account,
            "debit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": doc.asset,
        })
        je.append("accounts", {
            "account": wip_account,
            "credit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": doc.asset,
        })
    else:
        expense_account = category_account.custom_maintenance_expense_account
        if not expense_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Expense Account' on the Asset Category Account "
                    "for {0} / {1} before completing a repair without a linked Purchase Invoice."
                ).format(asset.asset_category, company),
                title=_("Missing Maintenance Expense Account"),
            )
        # لا نستخدم حساب موردين الشركة العام هنا: ERPNext يشترط تحديد طرف
        # (Party Type / Party) لأي قيد على حساب من نوع Payable/Receivable،
        # وإصلاح بدون فاتورة شراء ليس له مورد محدد أصلاً (لو كان له مورد،
        # كان المفروض يُفوتَر أصلاً بدل ما يمر من هنا). لذلك نستخدم حساب
        # التزامات مستحقة مخصص (Current Liability، وليس Payable) لا يحتاج
        # طرفاً — قرار تأكد من المستخدم صراحة.
        accrued_account = category_account.custom_maintenance_accrued_liability_account
        if not accrued_account:
            frappe.throw(
                _(
                    "Please set 'Maintenance Accrued Liability Account' on the Asset Category "
                    "Account for {0} / {1} before completing a non-capitalized repair without "
                    "a linked Purchase Invoice."
                ).format(asset.asset_category, company),
                title=_("Missing Accrued Liability Account"),
            )
        je.user_remark = _("Maintenance expense for Asset {0} via {1}").format(
            asset.asset_name, doc.name
        )
        je.append("accounts", {
            "account": expense_account,
            "debit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": doc.asset,
        })
        je.append("accounts", {
            "account": accrued_account,
            "credit_in_account_currency": total_cost,
            "cost_center": cost_center,
            "reference_type": "Asset",
            "reference_name": doc.asset,
        })

    je.insert(ignore_permissions=True)
    je.submit()

    doc.db_set("custom_journal_entry", je.name, update_modified=False)


def _cancel_repair_cost_gl_entry(doc):
    je_name = doc.get("custom_journal_entry")
    if not je_name or not frappe.db.exists("Journal Entry", je_name):
        return
    je = frappe.get_doc("Journal Entry", je_name)
    if je.docstatus == 1:
        je.cancel()


def _log_repair_activity(doc):
    """تسجيل ملخص الإصلاح في سجل نشاط الأصل."""
    labor = flt(doc.get("custom_labor_cost"))
    total = flt(doc.total_repair_cost) + labor
    technician = doc.get("custom_technician_name") or _("Unknown")

    subject = _(
        "Asset Repair {0} submitted – Status: {1} | Technician: {2} | Total Cost: {3}"
    ).format(doc.name, doc.repair_status, technician, total)

    frappe.get_doc(
        {
            "doctype": "Asset Activity",
            "asset": doc.asset,
            "subject": subject,
            "user": frappe.session.user,
            "date": now_datetime(),
        }
    ).insert(ignore_permissions=True, ignore_links=True)


# ---------------------------------------------------------------------------
# On Cancel
# ---------------------------------------------------------------------------

def on_cancel(doc, method=None):
    _update_asset_maintenance_summary(doc.asset)
    _cancel_repair_cost_gl_entry(doc)

    frappe.get_doc(
        {
            "doctype": "Asset Activity",
            "asset": doc.asset,
            "subject": _("Asset Repair {0} cancelled – maintenance totals recalculated.").format(doc.name),
            "user": frappe.session.user,
            "date": now_datetime(),
        }
    ).insert(ignore_permissions=True, ignore_links=True)
