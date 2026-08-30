"""
معالج البيانات التجريبية (Demo Data Wizard) — أداة داخل النظام يستخدمها مدير
النظام لإضافة بيانات تجريبية حقيقية (وليست rollback) عبر كل وحدات التطبيق،
خطوة بخطوة، ثم حذفها بالكامل بضغطة زر واحدة عند الانتهاء من الاختبار.

الفرق عن demo_test.py:
    - demo_test.py: يرجع كل شيء (rollback) في النهاية تلقائياً — للتحقق من
      المنطق فقط، بدون أي أثر دائم.
    - demo_wizard.py: يُنشئ بيانات فعلية وباقية في قاعدة البيانات، لكن كل
      مستند يُنشئه يُسجَّل في "Asset Demo Run Log" ليكون حذفه لاحقاً دقيقاً
      وآمناً (لا يمس أي بيانات حقيقية أخرى في النظام).

الاستخدام: من صفحة "معالج بيانات الأصول التجريبية" داخل النظام (Desk)،
لا يحتاج bench execute ولا وصول للسيرفر.
"""

import frappe
from frappe import _
from frappe.utils import today, now_datetime, add_days


# ---------------------------------------------------------------------------
# تسجيل كل مستند يُنشئه المعالج، لضمان حذف دقيق لاحقاً
# ---------------------------------------------------------------------------

def _log(step, doctype, name):
    if not name:
        return
    if frappe.db.exists("Asset Demo Run Log", {"reference_doctype": doctype, "reference_name": name}):
        return
    frappe.get_doc({
        "doctype": "Asset Demo Run Log",
        "step": step,
        "reference_doctype": doctype,
        "reference_name": name,
    }).insert(ignore_permissions=True)


class Reporter:
    def __init__(self):
        self.lines = []

    def ok(self, msg):
        self.lines.append({"level": "ok", "text": msg})

    def fail(self, msg):
        self.lines.append({"level": "fail", "text": msg})

    def skip(self, msg):
        self.lines.append({"level": "skip", "text": msg})

    def info(self, msg):
        self.lines.append({"level": "info", "text": msg})


def _guard():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("هذه الأداة متاحة فقط لمدير النظام (System Manager)."))


# ---------------------------------------------------------------------------
# بيانات أساسية مشتركة (Master Data) — تُستخدم كنقطة انطلاق لكل الخطوات
# ---------------------------------------------------------------------------

def _get_default_company():
    company = frappe.defaults.get_global_default("company")
    if company and frappe.db.exists("Company", company):
        return company
    return frappe.db.get_value("Company", {}, "name")


def _get_or_create_location(step="master"):
    loc = frappe.db.get_value("Location", {}, "name")
    if loc:
        return loc
    doc = frappe.get_doc({"doctype": "Location", "location_name": "موقع تجريبي - Demo Wizard"})
    doc.insert(ignore_permissions=True)
    _log(step, "Location", doc.name)
    return doc.name


def _get_or_create_second_location(exclude_location, step="movement_transfer"):
    loc = frappe.db.get_value("Location", {"name": ["!=", exclude_location]}, "name")
    if loc:
        return loc
    doc = frappe.get_doc({"doctype": "Location", "location_name": "موقع تجريبي 2 - Demo Wizard"})
    doc.insert(ignore_permissions=True)
    _log(step, "Location", doc.name)
    return doc.name


def _get_or_create_asset_category(company, step="master"):
    existing = frappe.db.get_value("Asset Category", {}, "name")
    if existing:
        return existing
    fixed_asset_account = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Fixed Asset", "is_group": 0}, "name"
    )
    if not fixed_asset_account:
        frappe.throw(_("لا يوجد أي حساب من نوع 'Fixed Asset' في شجرة حسابات الشركة — "
                       "يجب تجهيز الإعداد الأساسي (Chart of Accounts) أولاً قبل استخدام هذا المعالج."))
    cat = frappe.get_doc({
        "doctype": "Asset Category",
        "asset_category_name": "فئة تجريبية - Demo Wizard",
        "accounts": [{"company_name": company, "fixed_asset_account": fixed_asset_account}],
    })
    cat.insert(ignore_permissions=True)
    _log(step, "Asset Category", cat.name)
    return cat.name


def _get_or_create_fixed_asset_item(asset_category, step="master"):
    code = "DEMO-WIZARD-FIXED-ASSET-ITEM"
    if frappe.db.exists("Item", code):
        return code
    item_group = frappe.db.get_value("Item Group", {}, "name")
    if not item_group:
        frappe.throw(_("لا توجد أي مجموعة أصناف (Item Group) في النظام."))
    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": code,
        "item_name": "صنف أصل ثابت تجريبي - Demo Wizard",
        "item_group": item_group,
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "is_fixed_asset": 1,
        "asset_category": asset_category,
    })
    item.insert(ignore_permissions=True)
    _log(step, "Item", item.name)
    return item.name


def _get_or_create_branch(location, step="master"):
    branch = frappe.db.get_value("Branch", {}, "name")
    if branch:
        if not frappe.db.get_value("Branch", branch, "custom_default_location"):
            frappe.db.set_value("Branch", branch, "custom_default_location", location)
        return branch
    doc = frappe.get_doc({
        "doctype": "Branch",
        "branch": "فرع تجريبي - Demo Wizard",
        "custom_default_location": location,
    })
    doc.insert(ignore_permissions=True)
    _log(step, "Branch", doc.name)
    return doc.name


def _get_active_employee(company=None):
    if company:
        emp = frappe.db.get_value("Employee", {"status": "Active", "company": company}, "name")
        if emp:
            return emp
    return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _get_cost_center(company):
    return frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")


def _log_auto_receipt_movement(step, asset_name):
    """Asset.on_submit() ينشئ تلقائياً سند استلام (Receipt) معتمَد لكل أصل
    جديد — لازم نسجله عشان نقدر نحذفه بأمان قبل حذف الأصل نفسه لاحقاً."""
    mv = frappe.db.get_value("Asset Movement Item", {"asset": asset_name}, "parent")
    if mv:
        _log(step, "Asset Movement", mv)


def _create_asset(step, company, location, item_code, category, is_spare=0, amount=10000, name_suffix=""):
    cost_center = _get_cost_center(company)
    asset = frappe.get_doc({
        "doctype": "Asset",
        "asset_name": ("أصل احتياطي تجريبي" if is_spare else "أصل تجريبي") + f" - Demo Wizard{name_suffix}",
        "item_code": item_code,
        "asset_category": category,
        "company": company,
        "location": location,
        "cost_center": cost_center,
        "is_existing_asset": 1,
        "calculate_depreciation": 0,
        "gross_purchase_amount": amount,
        "available_for_use_date": today(),
        "asset_quantity": 1,
        "custom_is_spare": is_spare,
    })
    asset.insert(ignore_permissions=True)
    asset.submit()
    _log(step, "Asset", asset.name)
    _log_auto_receipt_movement(step, asset.name)
    return asset.name


def _bootstrap_master(step="master"):
    company = _get_default_company()
    if not company:
        frappe.throw(_("لا توجد أي شركة (Company) في النظام على الإطلاق."))
    category = _get_or_create_asset_category(company, step)
    item_code = _get_or_create_fixed_asset_item(category, step)
    location = _get_or_create_location(step)
    branch = _get_or_create_branch(location, step)
    return {
        "company": company,
        "category": category,
        "item_code": item_code,
        "location": location,
        "branch": branch,
    }


def _get_any_submitted_asset(company=None):
    """يُستخدم فقط كحل احتياطي عام (fallback) للتعبئة التلقائية للوحدات
    الفرعية البسيطة (مثلاً حقل Link->Asset في تقرير أو سجل مراقبة) — وليس
    لأي خطوة تُنشئ عليه حركة مالية أو دائمة."""
    filters = {"docstatus": 1, "status": ["not in", ["Scrapped", "Sold"]]}
    if company:
        filters["company"] = company
    return frappe.db.get_value("Asset", filters, "name")


def _get_or_create_submitted_asset(step, name_suffix=""):
    """يُنشئ دائماً أصلاً تجريبياً مخصَّصاً لهذه الأداة — لا يُعاد استخدام أي
    أصل حقيقي موجود بالفعل في النظام، حتى لا تُنشأ حركات مالية دائمة
    (إصلاح/شطب/إعارة/احتفاظ) على أصل إنتاجي حقيقي. البيانات هنا ليست
    rollback مثل demo_test.py، فلازم تبقى معزولة تماماً عن البيانات الحقيقية."""
    m = _bootstrap_master(step)
    return _create_asset(step, m["company"], m["location"], m["item_code"], m["category"], name_suffix=name_suffix)


# ---------------------------------------------------------------------------
# خطوة 1: البيانات الأساسية + أصل تجريبي معتمَد
# ---------------------------------------------------------------------------

def step_master(r: Reporter):
    m = _bootstrap_master("master")
    r.ok(f"الشركة: {m['company']} | فئة الأصل: {m['category']} | الصنف: {m['item_code']} | "
         f"الموقع: {m['location']} | الفرع: {m['branch']}")

    asset = _create_asset("master", m["company"], m["location"], m["item_code"], m["category"])
    r.ok(f"تم إنشاء واعتماد أصل تجريبي: {asset}")


# ---------------------------------------------------------------------------
# خطوة 2: سلسلة اعتماد طلب استحداث أصل (تمويل ← مدير فرع ← إدارة أصول)
# ---------------------------------------------------------------------------

def step_requisition_chain(r: Reporter):
    employee = _get_active_employee()
    if not employee:
        r.skip("لا يوجد موظف نشط (Active Employee) في النظام — هذا يحتاج بيانات موارد بشرية حقيقية.")
        return

    company = _get_default_company()
    category = _get_or_create_asset_category(company, "requisition_chain")

    doc = frappe.new_doc("Asset Requisition")
    doc.employee = employee
    doc.asset_category = category
    doc.request_date = today()
    doc.justification = "بيانات تجريبية تلقائية (Demo Wizard)"
    doc.insert(ignore_permissions=True)
    _log("requisition_chain", "Asset Requisition", doc.name)
    doc.submit()
    doc.approve_finance()
    doc.approve_branch_manager()
    doc.approve_asset_manager()
    doc.reload()
    if doc.status == "Approved":
        r.ok(f"طلب {doc.name}: اكتملت سلسلة الاعتماد الثلاثية وأصبح 'Approved'")
    else:
        r.fail(f"طلب {doc.name}: الحالة النهائية غير متوقعة = {doc.status}")

    doc2 = frappe.new_doc("Asset Requisition")
    doc2.employee = employee
    doc2.asset_category = category
    doc2.request_date = today()
    doc2.justification = "اختبار رفض — بيانات تجريبية (Demo Wizard)"
    doc2.insert(ignore_permissions=True)
    _log("requisition_chain", "Asset Requisition", doc2.name)
    doc2.submit()
    doc2.approve_finance()
    doc2.reload()
    doc2.reject("سبب رفض تجريبي (Demo Wizard)")
    doc2.reload()
    if doc2.status == "Rejected":
        r.ok(f"طلب {doc2.name}: تم رفضه بنجاح للتحقق من مسار الرفض")
    else:
        r.fail(f"طلب {doc2.name}: نتيجة الرفض غير متوقعة = {doc2.status}")


# ---------------------------------------------------------------------------
# خطوة 3: القيد المحاسبي لإصلاح أصل (OpEx / CapEx)
# ---------------------------------------------------------------------------

def step_repair_gl(r: Reporter):
    asset = _get_or_create_submitted_asset("repair_gl", " (إصلاح)")
    asset_doc = frappe.get_doc("Asset", asset)
    r.ok(f"الأصل المستخدم: {asset}")

    cat_acc = frappe.db.get_value(
        "Asset Category Account",
        {"parent": asset_doc.asset_category, "company_name": asset_doc.company},
        ["custom_maintenance_expense_account", "custom_maintenance_accrued_liability_account",
         "custom_capital_maintenance_wip_account"],
        as_dict=True,
    )
    if not cat_acc:
        r.skip("لا يوجد إعداد حسابات (Asset Category Account) لهذه الفئة — لازم يُضاف أولاً (Bootstrap).")
        return

    # OpEx
    try:
        repair = frappe.new_doc("Asset Repair")
        repair.asset = asset
        repair.failure_date = today()
        repair.completion_date = today()
        repair.repair_status = "Completed"
        repair.repair_cost = 500
        repair.capitalize_repair_cost = 0
        repair.custom_technician_name = "فني تجريبي"
        repair.custom_repair_notes = "بيانات تجريبية تلقائية (Demo Wizard)"
        repair.insert(ignore_permissions=True)
        _log("repair_gl", "Asset Repair", repair.name)
        repair.submit()
        repair.reload()
        if repair.custom_journal_entry:
            _log("repair_gl", "Journal Entry", repair.custom_journal_entry)
            r.ok(f"OpEx: تم إنشاء إصلاح {repair.name} + قيد يومية {repair.custom_journal_entry}")
        else:
            r.skip("OpEx: لم يُنشأ قيد يومية (حسابات الصيانة غير مكتملة على الفئة)")
    except Exception as e:
        r.fail(f"OpEx: فشل السيناريو — {e}")

    # CapEx
    try:
        repair2 = frappe.new_doc("Asset Repair")
        repair2.asset = asset
        repair2.failure_date = today()
        repair2.completion_date = today()
        repair2.repair_status = "Completed"
        repair2.repair_cost = 1000
        repair2.capitalize_repair_cost = 1
        repair2.increase_in_asset_life = 6
        repair2.custom_technician_name = "فني تجريبي"
        repair2.custom_repair_notes = "بيانات تجريبية تلقائية - رسملة (Demo Wizard)"
        repair2.insert(ignore_permissions=True)
        _log("repair_gl", "Asset Repair", repair2.name)
        repair2.submit()
        repair2.reload()
        if repair2.custom_journal_entry:
            _log("repair_gl", "Journal Entry", repair2.custom_journal_entry)
            r.ok(f"CapEx: تم إنشاء إصلاح {repair2.name} + قيد يومية {repair2.custom_journal_entry}")
        else:
            r.skip("CapEx: لم يُنشأ قيد يومية (حساب الوساطة WIP غير معرَّف على الفئة)")
    except Exception as e:
        r.fail(f"CapEx: فشل السيناريو — {e}")


# ---------------------------------------------------------------------------
# خطوة 4: طلب احتفاظ بالعهدة (Asset Retention Request)
# ---------------------------------------------------------------------------

def step_retention(r: Reporter):
    asset = _get_or_create_submitted_asset("retention", " (احتفاظ)")
    asset_doc = frappe.get_doc("Asset", asset)
    employee = _get_active_employee(asset_doc.company)
    if not employee:
        r.skip("لا يوجد موظف نشط لتخصيص عهدة تجريبية له.")
        return

    am = frappe.get_doc({
        "doctype": "Asset Movement",
        "purpose": "Issue",
        "company": asset_doc.company,
        "transaction_date": now_datetime(),
        "assets": [{"asset": asset, "to_employee": employee}],
    })
    am.insert(ignore_permissions=True)
    _log("retention", "Asset Movement", am.name)
    am.submit()
    r.ok(f"تم تخصيص عهدة الأصل {asset} للموظف {employee} عبر سند {am.name}")

    retention = frappe.new_doc("Asset Retention Request")
    retention.employee = employee
    retention.asset = asset
    retention.travel_start = today()
    retention.travel_end = add_days(today(), 30)
    retention.destination = "بيانات تجريبية (Demo Wizard)"
    retention.justification = "بيانات تجريبية تلقائية (Demo Wizard)"
    retention.insert(ignore_permissions=True)
    _log("retention", "Asset Retention Request", retention.name)
    retention.db_set("status", "Approved")
    r.ok(f"تم إنشاء طلب احتفاظ بالعهدة {retention.name} وتعيينه 'Approved'")

    if frappe.db.get_value("Employee", employee, "relieving_date"):
        r.info("الموظف لديه بالفعل تاريخ إخلاء طرف — يمكنك إنشاء Full and Final Statement يدوياً "
               "للتحقق من استثناء هذه العهدة من المخالصة.")
    else:
        r.info("لتجربة استثناء هذه العهدة في المخالصة (Full and Final Statement)، يلزم أولاً ضبط "
               "'تاريخ إخلاء الطرف' على سجل الموظف الحقيقي يدوياً من HR — لن يقوم هذا المعالج بتعديل "
               "بيانات موظف حقيقي تلقائياً.")


# ---------------------------------------------------------------------------
# خطوة 5: الترميز (Coding) والتفعيل التشغيلي (Operational)
# ---------------------------------------------------------------------------

def step_coding_operational(r: Reporter):
    m = _bootstrap_master("coding_operational")
    asset_name = _create_asset(
        "coding_operational", m["company"], m["location"], m["item_code"], m["category"], name_suffix=" (ترميز)"
    )
    r.ok(f"أصل تجريبي جديد جاهز: {asset_name}")

    from asset_mgmt_custom.overrides.asset import mark_coded, set_operational

    frappe.db.set_value("Asset", asset_name, {
        "custom_tag_type": "Barcode",
        "custom_sticker_code": f"DEMO-{asset_name[-6:]}",
        "custom_tagging_photo_before": "/files/demo-before.jpg",
        "custom_tagging_photo": "/files/demo-after.jpg",
    })
    result = mark_coded(asset_name)
    if result == "Coded":
        r.ok(f"mark_coded: نجح، حالة الترميز أصبحت 'Coded' للأصل {asset_name}")
    else:
        r.fail(f"mark_coded: نتيجة غير متوقعة = {result}")
        return

    result2 = set_operational(asset_name)
    if result2 == "Operational":
        r.ok(f"set_operational: نجح، الأصل {asset_name} أصبح 'Operational'")
    else:
        r.fail(f"set_operational: نتيجة غير متوقعة = {result2}")


# ---------------------------------------------------------------------------
# خطوة 6: نقل أصل بين الفروع (Transfer) + تأكيد الاستلام
# ---------------------------------------------------------------------------

def step_movement_transfer(r: Reporter):
    asset_name = _get_or_create_submitted_asset("movement_transfer", " (نقل)")
    asset = frappe.get_doc("Asset", asset_name)
    target_location = _get_or_create_second_location(asset.location, "movement_transfer")

    movement = frappe.new_doc("Asset Movement")
    movement.purpose = "Transfer"
    movement.company = asset.company
    movement.transaction_date = now_datetime()
    movement.append("assets", {"asset": asset_name, "target_location": target_location})
    movement.insert(ignore_permissions=True)
    _log("movement_transfer", "Asset Movement", movement.name)
    movement.submit()
    asset.reload()
    r.ok(f"تم إنشاء سند نقل {movement.name} — حالة الأصل التشغيلية: {asset.custom_operational_status}")

    from asset_mgmt_custom.overrides.asset_movement import confirm_receipt
    confirmed = confirm_receipt(movement.name)
    asset.reload()
    if asset_name in (confirmed or []) and asset.custom_operational_status == "Operational":
        r.ok("تأكيد الاستلام: نجح، الأصل رجع 'Operational'")
    else:
        r.fail(f"تأكيد الاستلام: نتيجة غير متوقعة (status={asset.custom_operational_status})")


# ---------------------------------------------------------------------------
# خطوة 7: تنفيذ الطلب المعتمد (نقل أصل احتياطي / إنشاء طلب شراء)
# ---------------------------------------------------------------------------

def step_requisition_execution(r: Reporter):
    employee = _get_active_employee()
    if not employee:
        r.skip("لا يوجد موظف نشط في النظام.")
        return
    m = _bootstrap_master("requisition_execution")

    spare = _create_asset(
        "requisition_execution", m["company"], m["location"], m["item_code"], m["category"],
        is_spare=1, amount=5000, name_suffix=" (تنفيذ)"
    )
    r.ok(f"تم إنشاء أصل احتياطي معتمَد: {spare}")

    doc = frappe.new_doc("Asset Requisition")
    doc.employee = employee
    doc.branch = m["branch"]
    doc.asset_category = m["category"]
    doc.item_code = m["item_code"]
    doc.request_date = today()
    doc.justification = "بيانات تجريبية — تنفيذ عبر أصل احتياطي (Demo Wizard)"
    doc.insert(ignore_permissions=True)
    _log("requisition_execution", "Asset Requisition", doc.name)
    if not (doc.spare_available and doc.spare_asset == spare):
        r.fail(f"لم يُكتشف الأصل الاحتياطي تلقائياً (spare_available={doc.spare_available})")
        return
    r.ok(f"تم اكتشاف الأصل الاحتياطي تلقائياً: {doc.spare_asset}")

    doc.submit()
    doc.approve_finance()
    doc.approve_branch_manager()
    doc.approve_asset_manager()
    doc.reload()

    movement_name = doc.create_asset_movement()
    doc.reload()
    if movement_name and doc.status == "Fulfilled":
        _log("requisition_execution", "Asset Movement", movement_name)
        r.ok(f"create_asset_movement: تم إنشاء سند استلام {movement_name} وأصبح الطلب 'Fulfilled'")
    else:
        r.fail("create_asset_movement: نتيجة غير متوقعة")

    # سيناريو طلب شراء (بدون احتياطي/مخزون لنفس الصنف)
    doc2 = frappe.new_doc("Asset Requisition")
    doc2.employee = employee
    doc2.asset_category = m["category"]
    doc2.item_code = m["item_code"]
    doc2.quantity = 1
    doc2.request_date = today()
    doc2.justification = "بيانات تجريبية — تنفيذ عبر طلب شراء (Demo Wizard)"
    doc2.insert(ignore_permissions=True)
    _log("requisition_execution", "Asset Requisition", doc2.name)
    if doc2.spare_available or doc2.stock_available:
        r.info("سيناريو طلب الشراء: يوجد احتياطي/مخزون فعلي متاح بنفس الصنف — تم تخطي هذا الجزء.")
        return

    doc2.submit()
    doc2.approve_finance()
    doc2.approve_branch_manager()
    doc2.approve_asset_manager()
    doc2.reload()
    mr_name = doc2.create_purchase_requisition()
    doc2.reload()
    if mr_name and doc2.status == "Fulfilled":
        _log("requisition_execution", "Material Request", mr_name)
        r.ok(f"create_purchase_requisition: تم إنشاء طلب شراء {mr_name} وأصبح الطلب 'Fulfilled'")
    else:
        r.fail("create_purchase_requisition: نتيجة غير متوقعة")


# ---------------------------------------------------------------------------
# خطوة 8: شطب أصل (Asset Write-off Request)
# ---------------------------------------------------------------------------

def step_writeoff(r: Reporter):
    asset = _get_or_create_submitted_asset("writeoff", " (شطب)")

    wo = frappe.new_doc("Asset Write-off Request")
    wo.asset = asset
    wo.write_off_date = today()
    wo.reason = "Obsolete"
    wo.description = "بيانات تجريبية تلقائية (Demo Wizard)"
    wo.estimated_loss_value = 750
    wo.insert(ignore_permissions=True)
    _log("writeoff", "Asset Write-off Request", wo.name)
    wo.submit()
    wo.reload()
    r.ok(f"تم تقديم طلب الشطب {wo.name} — الحالة: {wo.status}")

    frappe.db.set_value("Asset Write-off Request", wo.name, "status", "Approved")
    wo.reload()
    je_name = wo.create_journal_entry()
    wo.reload()
    if je_name:
        _log("writeoff", "Journal Entry", je_name)
        r.ok(f"create_journal_entry: تم إنشاء قيد يومية {je_name} — حالة الطلب: {wo.status}")
    else:
        r.fail("create_journal_entry: لم يرجع اسم قيد يومية")


# ---------------------------------------------------------------------------
# خطوة 9: إعارة أصل (Asset Loan) واسترجاعها
# ---------------------------------------------------------------------------

def step_loan(r: Reporter):
    asset = _get_or_create_submitted_asset("loan", " (إعارة)")
    asset_doc = frappe.get_doc("Asset", asset)
    original_custodian = asset_doc.custodian
    employee = _get_active_employee(asset_doc.company)
    if not employee:
        r.skip("لا يوجد موظف نشط لتجربة الإعارة عليه.")
        return

    loan = frappe.new_doc("Asset Loan")
    loan.asset = asset
    loan.loaned_to = employee
    loan.loan_date = today()
    loan.expected_return_date = add_days(today(), 7)
    loan.purpose = "بيانات تجريبية تلقائية (Demo Wizard)"
    loan.insert(ignore_permissions=True)
    _log("loan", "Asset Loan", loan.name)
    loan.submit()
    asset_doc.reload()
    r.ok(f"تم إعارة الأصل {asset} للموظف {employee} — العهدة الآن: {asset_doc.custodian}")

    loan.record_return(actual_return_date=today(), return_condition="Good")
    loan.reload()
    asset_doc.reload()
    if loan.status == "Returned" and asset_doc.custodian == (original_custodian or ""):
        r.ok(f"تم تسجيل الإرجاع بنجاح — العهدة رجعت إلى: {original_custodian or '(بدون)'}")
    else:
        r.fail(f"نتيجة الإرجاع غير متوقعة (status={loan.status}, custodian={asset_doc.custodian})")


# ---------------------------------------------------------------------------
# خطوة 10: تسليم/استلام عهدة فرع (Asset Handover)
# ---------------------------------------------------------------------------

def step_handover(r: Reporter):
    m = _bootstrap_master("handover")
    asset = _create_asset(
        "handover", m["company"], m["location"], m["item_code"], m["category"], name_suffix=" (تسليم)"
    )
    frappe.db.set_value("Asset", asset, "custom_branch", m["branch"])

    handover = frappe.new_doc("Asset Handover")
    handover.branch = m["branch"]
    handover.handover_date = today()
    handover.outgoing_manager = "مدير خارج تجريبي - Demo Wizard"
    handover.incoming_manager = "مدير وارد تجريبي - Demo Wizard"
    handover.append("items", {"asset": asset, "condition": "Good"})
    handover.insert(ignore_permissions=True)
    _log("handover", "Asset Handover", handover.name)
    handover.submit()
    handover.reload()
    if handover.status == "Completed":
        r.ok(f"تم إنشاء واعتماد محضر تسليم/استلام {handover.name} (عدد الأصول: {handover.total_assets})")
    else:
        r.fail(f"حالة محضر التسليم غير متوقعة = {handover.status}")


# ---------------------------------------------------------------------------
# خطوة 11: طلب وتنفيذ التخلص من أصل (Disposal Request + Execution)
# ---------------------------------------------------------------------------

def step_disposal(r: Reporter):
    m = _bootstrap_master("disposal")
    asset = _create_asset(
        "disposal", m["company"], m["location"], m["item_code"], m["category"], name_suffix=" (تخلص)"
    )

    req = frappe.new_doc("Asset Disposal Request")
    req.asset = asset
    req.disposal_date = today()
    req.disposal_reason = "End of Life"
    req.insert(ignore_permissions=True)
    _log("disposal", "Asset Disposal Request", req.name)
    req.submit()
    req.reload()
    r.ok(f"تم تقديم طلب التخلص {req.name} — الحالة: {req.status}")

    req.approve()
    req.reload()
    r.ok(f"تم اعتماد طلب التخلص {req.name} — الحالة: {req.status}")

    execution = frappe.new_doc("Asset Disposal Execution")
    execution.asset = asset
    execution.disposal_request = req.name
    execution.disposal_method = "Scrapped"
    execution.execution_date = today()
    execution.insert(ignore_permissions=True)
    _log("disposal", "Asset Disposal Execution", execution.name)
    execution.submit()
    execution.reload()
    req.reload()
    if execution.disposal_status == "Executed":
        r.ok(f"تم تنفيذ التخلص {execution.name} — حالة طلب التخلص الآن: {req.status}")
    else:
        r.fail(f"حالة تنفيذ التخلص غير متوقعة = {execution.disposal_status}")


# ---------------------------------------------------------------------------
# الخطوة الأخيرة: بقية الوحدات الفرعية (تعبئة تلقائية عامة)
# ---------------------------------------------------------------------------

HAND_CRAFTED_DOCTYPES = {
    "Asset Requisition", "Asset Repair", "Asset Retention Request", "Asset Movement",
    "Asset Write-off Request", "Asset Loan", "Asset Handover",
    "Asset Disposal Request", "Asset Disposal Execution",
}


def _get_or_create_supplier(step="generic_modules"):
    supplier = frappe.db.get_value("Supplier", {}, "name")
    if supplier:
        return supplier
    supplier_group = frappe.db.get_value("Supplier Group", {}, "name")
    if not supplier_group:
        return None
    doc = frappe.get_doc({
        "doctype": "Supplier",
        "supplier_name": "مورد تجريبي - Demo Wizard",
        "supplier_group": supplier_group,
        "supplier_type": "Company",
    })
    doc.insert(ignore_permissions=True)
    _log(step, "Supplier", doc.name)
    return doc.name


def _get_or_create_spare_part(step="generic_modules"):
    existing = frappe.db.get_value("Asset Spare Part", {}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Asset Spare Part",
        "item_name": "قطعة غيار تجريبية - Demo Wizard",
        "quantity": 10,
    })
    doc.insert(ignore_permissions=True)
    _log(step, "Asset Spare Part", doc.name)
    return doc.name


def _get_demo_asset():
    """يفضّل أي أصل أنشأته هذه الأداة نفسها (مسجَّل في السجل) على أي أصل
    حقيقي — تجنباً لإلحاق سجلات تجريبية (قراءات عدادات، سجلات وقود، إلخ)
    بأصل إنتاجي حقيقي عند تعبئة الوحدات الفرعية البسيطة تلقائياً."""
    demo_asset = frappe.db.get_value("Asset Demo Run Log", {"reference_doctype": "Asset"}, "reference_name")
    if demo_asset and frappe.db.exists("Asset", demo_asset):
        return demo_asset
    return _get_any_submitted_asset()


CORE_LINK_RESOLVERS = {
    "Company": lambda: _get_default_company(),
    "Employee": lambda: _get_active_employee(),
    "Branch": lambda: frappe.db.get_value("Branch", {}, "name"),
    "Supplier": _get_or_create_supplier,
    "Fiscal Year": lambda: frappe.db.get_value("Fiscal Year", {}, "name"),
    "Asset Category": lambda: frappe.db.get_value("Asset Category", {}, "name"),
    "User": lambda: frappe.session.user,
    "Cost Center": lambda: _get_cost_center(_get_default_company()),
    "Asset": _get_demo_asset,
    "Asset Spare Part": _get_or_create_spare_part,
}


def _list_generic_doctypes():
    names = frappe.get_all(
        "DocType",
        filters={"module": "Asset Mgmt Custom", "istable": 0, "issingle": 0},
        pluck="name",
    )
    return sorted(n for n in names if n not in HAND_CRAFTED_DOCTYPES and n != "Asset Demo Run Log")


def _generate_scalar(fieldtype, label, fieldname):
    if fieldtype == "Date":
        return today()
    if fieldtype == "Datetime":
        return now_datetime()
    if fieldtype == "Int":
        return 1
    if fieldtype in ("Float", "Currency", "Percent"):
        return 100
    if fieldtype == "Check":
        return 0
    if fieldtype == "Duration":
        return 3600
    if fieldtype in ("Small Text", "Text", "Long Text", "Text Editor", "Code", "Markdown Editor", "HTML Editor"):
        return f"بيانات تجريبية تلقائية (Demo Wizard) — {label or fieldname}"
    if fieldtype == "Data":
        return f"تجريبي - {label or fieldname}"
    return None


def _fill_select(field):
    options = [o.strip() for o in (field.options or "").split("\n") if o.strip()]
    return options[0] if options else None


def _resolve_link(field):
    target = field.options
    resolver = CORE_LINK_RESOLVERS.get(target)
    if resolver:
        try:
            val = resolver()
            if val:
                return val
        except Exception:
            pass
    try:
        return frappe.db.get_value(target, {}, "name")
    except Exception:
        return None


NON_FILLABLE_TYPES = ("Table", "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table MultiSelect")
SKIP_TYPES = ("Attach", "Attach Image", "Signature", "Image")


def run_generic_doctype(doctype_name, r: Reporter):
    meta = frappe.get_meta(doctype_name)
    doc = frappe.new_doc(doctype_name)
    missing = []
    for f in meta.fields:
        if not f.reqd or f.fieldtype in NON_FILLABLE_TYPES:
            continue
        if f.read_only or f.fetch_from:
            continue
        if doc.get(f.fieldname):
            continue
        if f.fieldtype in SKIP_TYPES:
            missing.append(f.fieldname)
            continue
        if f.fieldtype == "Link":
            val = _resolve_link(f)
            if not val:
                missing.append(f.fieldname)
                continue
            doc.set(f.fieldname, val)
        elif f.fieldtype == "Select":
            val = _fill_select(f)
            if val:
                doc.set(f.fieldname, val)
            else:
                missing.append(f.fieldname)
        else:
            val = _generate_scalar(f.fieldtype, f.label, f.fieldname)
            if val is not None:
                doc.set(f.fieldname, val)

    if missing:
        r.skip(f"{doctype_name}: تخطي — تعذّر توليد حقول إلزامية بأمان تلقائياً ({', '.join(missing)})")
        return

    try:
        doc.insert(ignore_permissions=True)
    except Exception as e:
        r.fail(f"{doctype_name}: فشل الإنشاء — {e}")
        return

    _log("generic_modules", doctype_name, doc.name)

    submitted = False
    if meta.is_submittable:
        try:
            doc.submit()
            submitted = True
        except Exception as e:
            r.info(f"{doctype_name}: تم الإنشاء {doc.name} لكن تعذّر اعتماده (Submit) — {e}")

    r.ok(f"{doctype_name}: تم إنشاء {doc.name}" + (" واعتماده" if submitted else ""))


def step_generic_modules(r: Reporter):
    doctypes = _list_generic_doctypes()
    r.info(f"عدد الوحدات الفرعية المتبقية: {len(doctypes)}")
    for dt in doctypes:
        try:
            run_generic_doctype(dt, r)
        except Exception as e:
            r.fail(f"{dt}: خطأ غير متوقع — {e}")


# ---------------------------------------------------------------------------
# سجل الخطوات — تُعرض في صفحة المعالج بهذا الترتيب
# ---------------------------------------------------------------------------

STEPS = [
    {"id": "master", "group": "الأساسيات", "title": "تجهيز البيانات الأساسية وأصل تجريبي", "fn": step_master},
    {"id": "requisition_chain", "group": "الأساسيات", "title": "سلسلة اعتماد طلب استحداث أصل", "fn": step_requisition_chain},
    {"id": "coding_operational", "group": "الأساسيات", "title": "الترميز (Coding) والتفعيل التشغيلي", "fn": step_coding_operational},
    {"id": "movement_transfer", "group": "الحركة والنقل", "title": "نقل أصل بين الفروع + تأكيد الاستلام", "fn": step_movement_transfer},
    {"id": "requisition_execution", "group": "الحركة والنقل", "title": "تنفيذ طلب معتمَد (أصل احتياطي / طلب شراء)", "fn": step_requisition_execution},
    {"id": "loan", "group": "الحركة والنقل", "title": "إعارة أصل واسترجاع العهدة", "fn": step_loan},
    {"id": "handover", "group": "الحركة والنقل", "title": "تسليم/استلام عهدة فرع (Handover)", "fn": step_handover},
    {"id": "repair_gl", "group": "المالية والمحاسبة", "title": "القيد المحاسبي لإصلاح أصل (OpEx / CapEx)", "fn": step_repair_gl},
    {"id": "retention", "group": "المالية والمحاسبة", "title": "طلب احتفاظ بعهدة (Asset Retention)", "fn": step_retention},
    {"id": "writeoff", "group": "المالية والمحاسبة", "title": "شطب أصل والقيد المحاسبي", "fn": step_writeoff},
    {"id": "disposal", "group": "المالية والمحاسبة", "title": "طلب وتنفيذ التخلص من أصل", "fn": step_disposal},
    {"id": "generic_modules", "group": "باقي الوحدات الفرعية", "title": "إنشاء سجل تجريبي واحد لكل وحدة فرعية متبقية", "fn": step_generic_modules},
]

_STEP_MAP = {s["id"]: s for s in STEPS}


@frappe.whitelist()
def get_steps():
    _guard()
    return [{"id": s["id"], "group": s["group"], "title": s["title"]} for s in STEPS]


@frappe.whitelist()
def run_step(step_id):
    _guard()
    step = _STEP_MAP.get(step_id)
    if not step:
        frappe.throw(_("خطوة غير معروفة: {0}").format(step_id))

    r = Reporter()
    try:
        step["fn"](r)
    except Exception as e:
        frappe.log_error(title=f"demo_wizard: step {step_id} failed")
        r.fail(f"خطأ غير متوقع أوقف الخطوة: {e}")
    return {"lines": r.lines}


@frappe.whitelist()
def get_summary():
    _guard()
    rows = frappe.db.sql(
        """
        SELECT reference_doctype, COUNT(*) AS cnt
        FROM `tabAsset Demo Run Log`
        GROUP BY reference_doctype
        ORDER BY reference_doctype
        """,
        as_dict=True,
    )
    total = sum(r.cnt for r in rows)
    return {"total": total, "by_doctype": rows}


@frappe.whitelist()
def cleanup_all():
    _guard()
    entries = frappe.get_all(
        "Asset Demo Run Log",
        fields=["name", "reference_doctype", "reference_name"],
        order_by="creation desc",
    )
    lines = []
    for e in entries:
        try:
            if frappe.db.exists(e.reference_doctype, e.reference_name):
                doc = frappe.get_doc(e.reference_doctype, e.reference_name)
                if doc.meta.is_submittable and doc.docstatus == 1:
                    doc.cancel()
                frappe.delete_doc(e.reference_doctype, e.reference_name, force=1,
                                   ignore_permissions=True, ignore_missing=True)
                lines.append({"level": "ok", "text": f"تم حذف {e.reference_doctype} — {e.reference_name}"})
            else:
                lines.append({"level": "skip", "text": f"{e.reference_doctype} — {e.reference_name}: محذوف مسبقاً"})
        except Exception as ex:
            lines.append({"level": "fail", "text": f"تعذّر حذف {e.reference_doctype} — {e.reference_name}: {ex}"})
        finally:
            frappe.delete_doc("Asset Demo Run Log", e.name, force=1, ignore_permissions=True, ignore_missing=True)

    # تنظيف إضافي: سجلات Asset Activity المتيتّمة التي أنشأها Handover لأصول تم حذفها
    try:
        frappe.db.sql(
            "DELETE FROM `tabAsset Activity` WHERE asset NOT IN (SELECT name FROM `tabAsset`)"
        )
    except Exception:
        pass

    frappe.db.commit()
    return {"lines": lines}
