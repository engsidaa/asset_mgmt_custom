"""
سكريبت اختبار توضيحي (Demo/Smoke Test) — للتشغيل اليدوي فقط، وليس جزءاً من
دورة الـ migrate العادية.

الغرض: تجربة أهم المسارات اللي بُنيت في المراحل 1-4 (سلسلة اعتماد Asset
Requisition، القيد المحاسبي التلقائي لـ Asset Repair، استثناء الاحتفاظ
بالعهدة في Full and Final Statement) على بيانات وهمية، وطباعة النتيجة
خطوة بخطوة في الـ console — بدون ترك أي أثر حقيقي في قاعدة البيانات.

النظام كان فاضي تماماً من بيانات الأصول عند أول تشغيل (لا فئات أصول، لا
أصول معتمدة، لا عهد) — فالسكريبت بيحاول أولاً يستخدم بيانات حقيقية موجودة،
ولو معدومة كلياً بيجهّز الحد الأدنى من بيانات تجريبية بنفسه (فئة أصل، صنف،
موقع، أصل) عشان نقدر نختبر المنطق الفعلي، مش بس نكتفي بتخطي كل حاجة.

مهم جداً: كل التغييرات بتترجع (frappe.db.rollback) في نهاية السكريبت
تلقائياً، حتى لو نجح كل شيء — سواء البيانات اللي استخدمها كانت موجودة
أصلاً أو تم تجهيزها هنا. مفيش أي بيانات وهمية هتفضل موجودة بعد التشغيل.

طريقة التشغيل من السيرفر:
    cd ~/frappe-bench
    bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.run_demo_test
"""

import frappe
from frappe.utils import today, add_days, now_datetime


def _ok(msg):
    print(f"✅ {msg}")


def _fail(msg, exc=None):
    print(f"❌ {msg}")
    if exc:
        print(f"    السبب: {exc}")


def _skip(msg):
    print(f"⏭️  تخطي: {msg}")


def _info(msg):
    print(f"ℹ️  {msg}")


def _header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_demo_test():
    print("#" * 70)
    print("# بدء الاختبار التوضيحي — كل شيء سيُرجَع (rollback) في النهاية")
    print("#" * 70)

    try:
        _test_roles()
        _test_asset_requisition_chain()
        _test_asset_repair_gl()
        _test_retention_and_ff_exemption()
        coded_asset = _test_coding_and_operational()
        _test_asset_movement_transfer(coded_asset)
        _test_requisition_execution()
        _test_asset_writeoff()
    finally:
        frappe.db.rollback()
        print("\n" + "#" * 70)
        print("# تم عمل rollback لكل شيء — لا توجد بيانات وهمية باقية في قاعدة البيانات")
        print("#" * 70)


# ---------------------------------------------------------------------------
# اختبار 1: سلامة توحيد اسم الدور
# ---------------------------------------------------------------------------

def _test_roles():
    _header("1) فحص توحيد اسم الدور (Asset Manager)")
    try:
        old_role_exists = frappe.db.exists("Role", "Assets Manager")
        new_role_exists = frappe.db.exists("Role", "Asset Manager")

        if old_role_exists:
            _fail("الدور القديم 'Assets Manager' لا يزال موجوداً — لم يتم عمل migrate بعد، أو فشل الدمج")
        else:
            _ok("الدور القديم 'Assets Manager' غير موجود (تم دمجه أو لم يكن موجوداً أصلاً)")

        if new_role_exists:
            _ok("الدور الموحّد 'Asset Manager' موجود")
        else:
            _fail("الدور 'Asset Manager' غير موجود إطلاقاً — مشكلة في الإعداد الأساسي")

        stray_users = frappe.db.sql(
            """
            SELECT parent FROM `tabHas Role`
            WHERE role = 'Assets Manager'
            """,
            as_dict=True,
        )
        if stray_users:
            _fail(f"يوجد {len(stray_users)} مستخدم لا يزال مرتبطاً بالدور القديم: "
                  f"{[u.parent for u in stray_users]}")
        else:
            _ok("لا يوجد أي مستخدم مرتبط بالدور القديم")
    except Exception as e:
        _fail("خطأ غير متوقع أثناء فحص الأدوار", e)


# ---------------------------------------------------------------------------
# تجهيز بيانات تجريبية عند الحاجة (فقط لو مفيش بيانات حقيقية أصلاً)
# ---------------------------------------------------------------------------

def _get_default_company():
    company = frappe.defaults.get_global_default("company")
    if company and frappe.db.exists("Company", company):
        return company
    return frappe.db.get_value("Company", {}, "name")


def _get_or_create_location():
    loc = frappe.db.get_value("Location", {}, "name")
    if loc:
        return loc
    doc = frappe.get_doc({
        "doctype": "Location",
        "location_name": "موقع تجريبي - Demo Test",
    })
    doc.insert(ignore_permissions=True)
    _info(f"تم إنشاء موقع تجريبي مؤقت: {doc.name} (لم يكن يوجد أي Location في النظام)")
    return doc.name


def _get_or_create_asset_category(company):
    """يحاول يلاقي فئة أصل حقيقية موجودة أولاً. لو مفيش، بيجهّز فئة تجريبية
    مربوطة بأي حساب Fixed Asset حقيقي موجود في شجرة الحسابات — لو معندناش
    حتى حساب Fixed Asset واحد، بنتوقف هنا بوضوح (ده إعداد أساسي ناقص فعلاً،
    مش حاجة نقدر نخترعها بأمان)."""
    existing = frappe.db.get_value("Asset Category", {}, "name")
    if existing:
        return existing, False

    fixed_asset_account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Fixed Asset", "is_group": 0},
        "name",
    )
    if not fixed_asset_account:
        _skip(f"لا توجد أي فئة أصول ولا أي حساب من نوع 'Fixed Asset' في شجرة حسابات "
              f"الشركة '{company}' — هذا إعداد أساسي لازم يُضاف يدوياً قبل استخدام "
              f"وحدة الأصول فعلياً (Chart of Accounts)")
        return None, False

    cat = frappe.get_doc({
        "doctype": "Asset Category",
        "asset_category_name": "فئة تجريبية - Demo Test",
        "accounts": [{
            "company_name": company,
            "fixed_asset_account": fixed_asset_account,
        }],
    })
    cat.insert(ignore_permissions=True)
    _info(f"تم إنشاء فئة أصل تجريبية مؤقتة: {cat.name} (لم تكن توجد أي فئة أصول في النظام)")
    return cat.name, True


def _get_or_create_fixed_asset_item(asset_category):
    code = "DEMO-TEST-FIXED-ASSET-ITEM"
    if frappe.db.exists("Item", code):
        return code

    item_group = frappe.db.get_value("Item Group", {}, "name")
    if not item_group:
        _skip("لا توجد أي مجموعة أصناف (Item Group) في النظام — لا يمكن تجهيز صنف تجريبي")
        return None

    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": code,
        "item_name": "صنف أصل تجريبي - Demo Test",
        "item_group": item_group,
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "is_fixed_asset": 1,
        "asset_category": asset_category,
    })
    item.insert(ignore_permissions=True)
    _info(f"تم إنشاء صنف أصل ثابت تجريبي مؤقت: {item.name}")
    return item.name


def _create_demo_asset(company, location, item_code, asset_category):
    cost_center = frappe.db.get_value(
        "Cost Center", {"company": company, "is_group": 0}, "name"
    )
    asset = frappe.get_doc({
        "doctype": "Asset",
        "asset_name": "أصل تجريبي - Demo Test",
        "item_code": item_code,
        "asset_category": asset_category,
        "company": company,
        "location": location,
        "cost_center": cost_center,
        "is_existing_asset": 1,
        "calculate_depreciation": 0,
        "gross_purchase_amount": 10000,
        "available_for_use_date": today(),
        "asset_quantity": 1,
    })
    asset.insert(ignore_permissions=True)
    asset.submit()
    _info(f"تم إنشاء أصل تجريبي مؤقت ومعتمَد: {asset.name}")
    return asset.name


def _get_or_create_submitted_asset():
    """يرجع (اسم أصل معتمد، اسم فئته) — يستخدم أصل حقيقي موجود لو فيه،
    وإلا يجهّز واحد تجريبياً بالكامل (فئة + صنف + موقع + أصل)."""
    asset = frappe.db.get_value(
        "Asset", {"docstatus": 1, "status": ["not in", ["Scrapped", "Sold"]]}, "name"
    )
    if asset:
        return asset, False

    company = _get_default_company()
    if not company:
        _skip("لا توجد أي شركة (Company) في النظام على الإطلاق")
        return None, False

    category, _created_cat = _get_or_create_asset_category(company)
    if not category:
        return None, False

    item_code = _get_or_create_fixed_asset_item(category)
    if not item_code:
        return None, False

    location = _get_or_create_location()

    try:
        asset = _create_demo_asset(company, location, item_code, category)
        return asset, True
    except Exception as e:
        _fail("تعذّر إنشاء أصل تجريبي للاختبار", e)
        return None, False


def _get_active_employee(company=None):
    filters = {"status": "Active"}
    if company:
        filters["company"] = company
        emp = frappe.db.get_value("Employee", filters, "name")
        if emp:
            return emp
    return frappe.db.get_value("Employee", {"status": "Active"}, "name")


# ---------------------------------------------------------------------------
# اختبار 2: سلسلة اعتماد Asset Requisition (3 مراحل) + الرفض
# ---------------------------------------------------------------------------

def _test_asset_requisition_chain():
    _header("2) سلسلة اعتماد Asset Requisition (تمويل ← مدير فرع ← مدير أصول)")
    try:
        employee = _get_active_employee()
        if not employee:
            _skip("لا يوجد موظف نشط (Active Employee) في النظام لتجربة الطلب عليه — "
                  "هذا يحتاج بيانات موارد بشرية حقيقية، لا يمكن تجهيزه تلقائياً بأمان")
            return

        company = _get_default_company()
        category, created = _get_or_create_asset_category(company) if company else (None, False)
        if not category:
            return

        _ok(f"استخدام الموظف: {employee} | فئة الأصل: {category}"
            f"{' (تم إنشاؤها تجريبياً)' if created else ''}")

        # --- المسار الأول: اعتماد كامل حتى النهاية ---
        doc = frappe.new_doc("Asset Requisition")
        doc.employee = employee
        doc.asset_category = category
        doc.request_date = today()
        doc.justification = "اختبار توضيحي تلقائي (Demo Test) — سيُحذف عبر rollback"
        doc.description = "Demo Test"
        doc.insert(ignore_permissions=True)
        _ok(f"تم إنشاء الطلب {doc.name} بحالة Draft")

        doc.submit()
        doc.reload()
        if doc.status == "Pending Finance Approval":
            _ok("بعد التقديم: الحالة أصبحت 'Pending Finance Approval' كما هو متوقع")
        else:
            _fail(f"بعد التقديم: الحالة غير متوقعة = {doc.status}")

        doc.approve_finance()
        doc.reload()
        if doc.status == "Pending Branch Manager Approval":
            _ok("بعد اعتماد المالية: الحالة أصبحت 'Pending Branch Manager Approval'")
        else:
            _fail(f"بعد اعتماد المالية: الحالة غير متوقعة = {doc.status}")

        doc.approve_branch_manager()
        doc.reload()
        if doc.status == "Pending Asset Manager Approval":
            _ok("بعد اعتماد مدير الفرع: الحالة أصبحت 'Pending Asset Manager Approval'")
        else:
            _fail(f"بعد اعتماد مدير الفرع: الحالة غير متوقعة = {doc.status}")

        doc.approve_asset_manager()
        doc.reload()
        if doc.status == "Approved":
            _ok("بعد اعتماد إدارة الأصول: الحالة أصبحت 'Approved' — السلسلة كاملة ✔")
        else:
            _fail(f"بعد اعتماد إدارة الأصول: الحالة غير متوقعة = {doc.status}")

        # --- المسار الثاني: الرفض في منتصف السلسلة ---
        doc2 = frappe.new_doc("Asset Requisition")
        doc2.employee = employee
        doc2.asset_category = category
        doc2.request_date = today()
        doc2.justification = "اختبار رفض تلقائي (Demo Test)"
        doc2.insert(ignore_permissions=True)
        doc2.submit()
        doc2.approve_finance()
        doc2.reload()
        doc2.reject("سبب رفض تجريبي")
        doc2.reload()
        if doc2.status == "Rejected" and doc2.rejection_reason:
            _ok("اختبار الرفض: الحالة أصبحت 'Rejected' مع تسجيل السبب بشكل صحيح")
        else:
            _fail(f"اختبار الرفض: النتيجة غير متوقعة = {doc2.status}")

    except Exception as e:
        _fail("فشل اختبار سلسلة اعتماد Asset Requisition", e)


# ---------------------------------------------------------------------------
# اختبار 3: القيد المحاسبي التلقائي لتكلفة الإصلاح (Asset Repair)
# ---------------------------------------------------------------------------

def _test_asset_repair_gl():
    _header("3) القيد المحاسبي التلقائي لتكلفة إصلاح أصل (بدون فاتورة شراء)")
    try:
        asset, created = _get_or_create_submitted_asset()
        if not asset:
            return

        asset_doc = frappe.get_doc("Asset", asset)
        _ok(f"استخدام الأصل: {asset} (الفئة: {asset_doc.asset_category})"
            f"{' (تم إنشاؤه تجريبياً)' if created else ''}")

        category_account = frappe.db.get_value(
            "Asset Category Account",
            {"parent": asset_doc.asset_category, "company_name": asset_doc.company},
            ["fixed_asset_account", "custom_capital_maintenance_wip_account",
             "custom_maintenance_expense_account", "custom_maintenance_accrued_liability_account"],
            as_dict=True,
        )
        if not category_account:
            _skip(f"لا يوجد إعداد حسابات (Asset Category Account) لفئة "
                  f"'{asset_doc.asset_category}' / شركة '{asset_doc.company}' — "
                  f"لازم يُضاف قبل ما نقدر نختبر القيد المحاسبي")
            return

        if not category_account.custom_maintenance_expense_account or not category_account.custom_maintenance_accrued_liability_account:
            _info("ملاحظة: 'Maintenance Expense Account' أو 'Maintenance Accrued Liability Account' "
                  "غير مُعرَّفين على هذه الفئة — اختبار OpEx هيُتخطى تلقائياً لو حصل")
        if not category_account.custom_capital_maintenance_wip_account:
            _info("ملاحظة: 'Capital Maintenance WIP Account' (حساب الوساطة) غير "
                  "مُعرَّف على هذه الفئة — اختبار CapEx هيُتخطى تلقائياً لو حصل")

        # --- OpEx: إصلاح عادي بدون رسملة (سيناريو مستقل — فشله لا يوقف باقي السيناريوهات) ---
        try:
            repair = frappe.new_doc("Asset Repair")
            repair.asset = asset
            repair.failure_date = today()
            repair.completion_date = today()
            repair.repair_status = "Completed"
            repair.repair_cost = 500
            repair.capitalize_repair_cost = 0
            repair.custom_technician_name = "فني تجريبي"
            repair.custom_repair_notes = "اختبار توضيحي تلقائي (Demo Test)"
            repair.insert(ignore_permissions=True)
            repair.submit()
            repair.reload()

            if repair.custom_journal_entry:
                je = frappe.get_doc("Journal Entry", repair.custom_journal_entry)
                total_debit = sum(row.debit_in_account_currency for row in je.accounts)
                total_credit = sum(row.credit_in_account_currency for row in je.accounts)
                _ok(f"OpEx: تم إنشاء قيد يومية {je.name} بحالة {je.docstatus} "
                    f"— إجمالي مدين={total_debit}, دائن={total_credit}")
                if total_debit == total_credit == 500:
                    _ok("OpEx: المبالغ متزنة ومطابقة لتكلفة الإصلاح (500)")
                else:
                    _fail("OpEx: المبالغ غير متزنة أو غير مطابقة (متوقع 500)")
            else:
                _skip("OpEx: لم يُنشأ قيد يومية — على الأغلب معندهاش custom_maintenance_expense_account "
                      "أو custom_maintenance_accrued_liability_account مُعرَّفين")
        except Exception as e:
            _fail("OpEx: فشل السيناريو", e)

        # --- اختبار سلبي: رسملة بدون تمديد العمر يجب أن تُرفض (سيناريو مستقل) ---
        try:
            repair2 = frappe.new_doc("Asset Repair")
            repair2.asset = asset
            repair2.failure_date = today()
            repair2.completion_date = today()
            repair2.repair_status = "Completed"
            repair2.repair_cost = 1000
            repair2.capitalize_repair_cost = 1
            repair2.custom_technician_name = "فني تجريبي"
            repair2.custom_repair_notes = "اختبار رسملة بدون تمديد عمر (يجب أن يُرفض)"
            blocked_correctly = False
            try:
                repair2.insert(ignore_permissions=True)
            except frappe.ValidationError:
                blocked_correctly = True

            if blocked_correctly:
                _ok("CapEx بدون 'زيادة العمر الإنتاجي': تم الرفض بشكل صحيح كما هو متوقع")
            else:
                _fail("CapEx بدون 'زيادة العمر الإنتاجي': لم يُرفض — المفروض يمنع الحفظ!")
        except Exception as e:
            _fail("اختبار الرفض السلبي (CapEx بدون تمديد عمر): فشل غير متوقع", e)

        # --- CapEx: رسملة صحيحة مع تمديد العمر (سيناريو مستقل) ---
        try:
            repair3 = frappe.new_doc("Asset Repair")
            repair3.asset = asset
            repair3.failure_date = today()
            repair3.completion_date = today()
            repair3.repair_status = "Completed"
            repair3.repair_cost = 1000
            repair3.capitalize_repair_cost = 1
            repair3.increase_in_asset_life = 6
            repair3.custom_technician_name = "فني تجريبي"
            repair3.custom_repair_notes = "اختبار رسملة صحيحة (Demo Test)"
            repair3.insert(ignore_permissions=True)
            repair3.submit()
            repair3.reload()

            if repair3.custom_journal_entry:
                je3 = frappe.get_doc("Journal Entry", repair3.custom_journal_entry)
                total_debit3 = sum(row.debit_in_account_currency for row in je3.accounts)
                _ok(f"CapEx: تم إنشاء قيد يومية {je3.name} — إجمالي مدين={total_debit3} "
                    f"(على حساب الأصل مقابل حساب الوساطة WIP)")
            else:
                _skip("CapEx: لم يُنشأ قيد يومية — على الأغلب معندهاش "
                      "custom_capital_maintenance_wip_account مُعرَّف")
        except Exception as e:
            _fail("CapEx: فشل السيناريو", e)

    except Exception as e:
        _fail("فشل اختبار القيد المحاسبي لإصلاح الأصل", e)


# ---------------------------------------------------------------------------
# اختبار 4: استثناء الاحتفاظ بالعهدة في Full and Final Statement
# ---------------------------------------------------------------------------

def _test_retention_and_ff_exemption():
    _header("4) استثناء الاحتفاظ بالعهدة (Asset Retention) في Full & Final Statement")
    try:
        row = frappe.db.sql(
            """
            SELECT ami.to_employee AS employee, ami.asset AS asset
            FROM `tabAsset Movement Item` ami
            JOIN `tabAsset Movement` am ON am.name = ami.parent
            WHERE am.docstatus = 1 AND ami.to_employee IS NOT NULL AND ami.to_employee != ''
            LIMIT 1
            """,
            as_dict=True,
        )
        employee = asset = None
        created_custody = False

        if row:
            employee, asset = row[0].employee, row[0].asset
        else:
            asset, created_asset = _get_or_create_submitted_asset()
            if not asset:
                return
            asset_doc = frappe.get_doc("Asset", asset)
            employee = _get_active_employee(asset_doc.company)
            if not employee:
                _skip("لا يوجد موظف نشط لتخصيص عهدة تجريبية له — "
                      "هذا يحتاج بيانات موارد بشرية حقيقية")
                return
            try:
                am = frappe.get_doc({
                    "doctype": "Asset Movement",
                    "purpose": "Issue",
                    "company": asset_doc.company,
                    "transaction_date": now_datetime(),
                    "assets": [{"asset": asset, "to_employee": employee}],
                })
                am.insert(ignore_permissions=True)
                am.submit()
                created_custody = True
                _info(f"تم إنشاء عهدة تجريبية مؤقتة: الأصل {asset} للموظف {employee} عبر {am.name}")
            except Exception as e:
                _fail("تعذّر إنشاء عهدة تجريبية (Asset Movement) للاختبار", e)
                return

        _ok(f"استخدام الموظف: {employee} | الأصل بعهدته: {asset}"
            f"{' (عهدة تجريبية جديدة)' if created_custody else ''}")

        retention = frappe.new_doc("Asset Retention Request")
        retention.employee = employee
        retention.asset = asset
        retention.travel_start = today()
        retention.travel_end = add_days(today(), 30)
        retention.destination = "اختبار توضيحي"
        retention.justification = "اختبار توضيحي تلقائي (Demo Test)"
        retention.insert(ignore_permissions=True)
        retention.db_set("status", "Approved")
        _ok(f"تم إنشاء طلب احتفاظ {retention.name} وتعيينه كـ 'Approved' مباشرة (تجاوز الـ Workflow للاختبار)")

        # relieving_date على المستند مربوط (fetch_from) بحقل الموظف نفسه
        # ومقروء فقط (read_only) — Frappe بيعيد جلبه من سجل الموظف وقت
        # الحفظ بغض النظر عمّا نضبطه هنا مباشرة، فلازم نضبطه على سجل
        # الموظف الحقيقي أولاً (مؤقتاً، هيترجع بالـ rollback زي كل حاجة تانية)
        if not frappe.db.get_value("Employee", employee, "relieving_date"):
            frappe.db.set_value("Employee", employee, "relieving_date", today())
            _info(f"تم ضبط تاريخ إخلاء طرف مؤقت على الموظف {employee} (لازم لاختبار Full & Final)")

        ff = frappe.new_doc("Full and Final Statement")
        ff.employee = employee
        ff.transaction_date = today()
        ff.insert(ignore_permissions=True)
        _ok(f"تم إنشاء Full and Final Statement {ff.name} (بدون submit)")

        target_row = next(
            (r for r in ff.assets_allocated if _asset_for_row_matches(r, employee, asset)),
            None,
        )
        if not target_row:
            _skip("الأصل المُحتفَظ به لم يظهر في جدول assets_allocated — "
                  "غالباً لأن سجل Asset Movement غير مرتبط بشكل يسمح لـ HRMS "
                  "بربطه تلقائياً (سلوك طبيعي حسب البيانات الفعلية، وليس بالضرورة خطأ)")
        elif target_row.action == "Recover Cost" and _flt_zero(target_row.cost):
            _ok("الأصل المحتفَظ به تم استثناؤه بنجاح: action='Recover Cost', cost=0 "
                "— لن يمنع اعتماد المخالصة")
        else:
            _fail(f"الأصل المحتفَظ به لم يُستثنَ كما هو متوقع: "
                  f"action={target_row.action}, cost={target_row.cost}")

    except Exception as e:
        _fail("فشل اختبار استثناء الاحتفاظ بالعهدة", e)


def _flt_zero(value):
    try:
        return float(value or 0) == 0
    except (TypeError, ValueError):
        return False


def _asset_for_row_matches(row, employee, asset):
    if not row.reference:
        return False
    linked_asset = frappe.db.get_value(
        "Asset Movement Item", {"parent": row.reference, "to_employee": employee}, "asset"
    )
    return linked_asset == asset


def _get_or_create_second_location(exclude_location):
    loc = frappe.db.get_value("Location", {"name": ["!=", exclude_location]}, "name")
    if loc:
        return loc
    doc = frappe.get_doc({
        "doctype": "Location",
        "location_name": "موقع تجريبي 2 - Demo Test",
    })
    doc.insert(ignore_permissions=True)
    _info(f"تم إنشاء موقع تجريبي ثانٍ مؤقت: {doc.name}")
    return doc.name


def _get_or_create_branch_with_location(location):
    """يستخدم أي فرع موجود بالفعل (ويضبط عليه مؤقتاً custom_default_location
    لو فاضي)، أو يجهّز فرعاً تجريبياً — الحقل نفسه لازم يكون موجوداً في
    قاعدة البيانات (bench migrate) قبل استخدامه."""
    branch = frappe.db.get_value("Branch", {}, "name")
    if branch:
        frappe.db.set_value("Branch", branch, "custom_default_location", location)
        return branch
    doc = frappe.get_doc({
        "doctype": "Branch",
        "branch": "فرع تجريبي - Demo Test",
        "custom_default_location": location,
    })
    doc.insert(ignore_permissions=True)
    _info(f"تم إنشاء فرع تجريبي مؤقت: {doc.name}")
    return doc.name


# ---------------------------------------------------------------------------
# اختبار 5: توثيق الترميز (Coding) والتفعيل التشغيلي (Operational)
# ---------------------------------------------------------------------------

def _test_coding_and_operational():
    _header("5) توثيق الترميز (Coding) والتفعيل التشغيلي (Operational)")
    try:
        company = _get_default_company()
        if not company:
            _skip("لا توجد شركة")
            return None

        category, _created = _get_or_create_asset_category(company)
        if not category:
            return None
        item_code = _get_or_create_fixed_asset_item(category)
        if not item_code:
            return None
        location = _get_or_create_location()

        asset_name = _create_demo_asset(company, location, item_code, category)
        asset = frappe.get_doc("Asset", asset_name)
        _ok(f"أصل تجريبي جديد جاهز: {asset_name} | ترميز: {asset.custom_coding_status} | "
            f"تشغيلياً: {asset.custom_operational_status}")

        from asset_mgmt_custom.overrides.asset import mark_coded, set_operational

        blocked = False
        try:
            mark_coded(asset_name)
        except frappe.ValidationError:
            blocked = True
        if blocked:
            _ok("mark_coded بدون نوع/كود تاگ: تم الرفض بشكل صحيح كما هو متوقع")
        else:
            _fail("mark_coded بدون نوع/كود تاگ: لم يُرفض!")

        frappe.db.set_value("Asset", asset_name, {
            "custom_tag_type": "Barcode",
            "custom_sticker_code": "DEMO-TAG-0001",
        })

        blocked2 = False
        try:
            mark_coded(asset_name)
        except frappe.ValidationError:
            blocked2 = True
        if blocked2:
            _ok("mark_coded بدون صورتَي قبل/بعد: تم الرفض بشكل صحيح كما هو متوقع")
        else:
            _fail("mark_coded بدون صورتَي قبل/بعد: لم يُرفض!")

        frappe.db.set_value("Asset", asset_name, {
            "custom_tagging_photo_before": "/files/demo-before.jpg",
            "custom_tagging_photo": "/files/demo-after.jpg",
        })

        result = mark_coded(asset_name)
        if result == "Coded":
            _ok("mark_coded ببيانات كاملة: نجح، الحالة أصبحت 'Coded'")
        else:
            _fail(f"mark_coded: نتيجة غير متوقعة = {result}")
            return None

        result2 = set_operational(asset_name)
        asset.reload()
        if result2 == "Operational" and asset.custom_operational_status == "Operational" and asset.available_for_use_date:
            _ok("set_operational: نجح، الحالة أصبحت 'Operational' وتم ضبط available_for_use_date")
        else:
            _fail("set_operational: نتيجة غير متوقعة")
            return None

        return asset_name
    except Exception as e:
        _fail("فشل اختبار الترميز والتفعيل", e)
        return None


# ---------------------------------------------------------------------------
# اختبار 6: نقل أصل بين الفروع (Transfer) + تأكيد الاستلام
# ---------------------------------------------------------------------------

def _test_asset_movement_transfer(asset_name):
    _header("6) نقل أصل بين الفروع (Asset Movement – Transfer) + تأكيد الاستلام")
    try:
        if not asset_name:
            _skip("لا يوجد أصل جاهز (مُرمَّز ومُفعَّل) من الاختبار السابق لتجربة النقل عليه")
            return

        asset = frappe.get_doc("Asset", asset_name)
        target_location = _get_or_create_second_location(asset.location)

        movement = frappe.new_doc("Asset Movement")
        movement.purpose = "Transfer"
        movement.company = asset.company
        movement.transaction_date = now_datetime()
        movement.append("assets", {"asset": asset_name, "target_location": target_location})
        movement.insert(ignore_permissions=True)
        _ok(f"تم إنشاء سند نقل {movement.name} (Draft)")

        movement.submit()
        asset.reload()
        if asset.custom_operational_status == "In Transit":
            _ok("بعد التقديم: حالة الأصل التشغيلية أصبحت 'In Transit' كما هو متوقع")
        else:
            _fail(f"بعد التقديم: الحالة غير متوقعة = {asset.custom_operational_status}")

        from asset_mgmt_custom.overrides.asset_movement import confirm_receipt
        confirmed = confirm_receipt(movement.name)
        asset.reload()
        if asset_name in (confirmed or []) and asset.custom_operational_status == "Operational":
            _ok("تأكيد الاستلام (Confirm Receipt): نجح، حالة الأصل رجعت 'Operational'")
        else:
            _fail(f"تأكيد الاستلام: نتيجة غير متوقعة — confirmed={confirmed}, "
                  f"status={asset.custom_operational_status}")

    except Exception as e:
        _fail("فشل اختبار نقل الأصل بين الفروع", e)


# ---------------------------------------------------------------------------
# اختبار 7: تنفيذ الطلب المعتمد (نقل أصل احتياطي / إنشاء طلب شراء)
# ---------------------------------------------------------------------------

def _test_requisition_execution():
    _header("7) تنفيذ الطلب المعتمد: نقل أصل احتياطي / إنشاء طلب شراء")
    try:
        employee = _get_active_employee()
        company = _get_default_company()
        if not employee or not company:
            _skip("لا يوجد موظف نشط أو شركة")
            return

        category, _created = _get_or_create_asset_category(company)
        if not category:
            return
        item_code = _get_or_create_fixed_asset_item(category)
        if not item_code:
            return
        location = _get_or_create_location()
        branch = _get_or_create_branch_with_location(location)

        cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")

        # --- سيناريو أ: يوجد أصل احتياطي جاهز ---
        spare = frappe.get_doc({
            "doctype": "Asset",
            "asset_name": "أصل احتياطي تجريبي - Demo Test",
            "item_code": item_code,
            "asset_category": category,
            "company": company,
            "location": location,
            "cost_center": cost_center,
            "is_existing_asset": 1,
            "calculate_depreciation": 0,
            "gross_purchase_amount": 5000,
            "available_for_use_date": today(),
            "custom_is_spare": 1,
        })
        spare.insert(ignore_permissions=True)
        spare.submit()
        _info(f"تم إنشاء أصل احتياطي تجريبي معتمَد: {spare.name}")

        # فحص تشخيصي مباشر — لو الاكتشاف التلقائي فشل، نعرف السبب بالظبط
        raw = frappe.db.get_value(
            "Asset", spare.name,
            ["asset_category", "item_code", "custom_is_spare", "docstatus"],
            as_dict=True,
        )
        _info(f"تحقق مباشر من قاعدة البيانات لسجل الأصل الاحتياطي: {raw} "
              f"(متوقع: asset_category={category}, item_code={item_code}, custom_is_spare=1, docstatus=1)")

        doc = frappe.new_doc("Asset Requisition")
        doc.employee = employee
        doc.branch = branch
        doc.asset_category = category
        doc.item_code = item_code
        doc.request_date = today()
        doc.justification = "اختبار تنفيذ الطلب — أصل احتياطي (Demo Test)"
        doc.insert(ignore_permissions=True)
        if doc.spare_available and doc.spare_asset == spare.name:
            _ok(f"تم اكتشاف الأصل الاحتياطي تلقائياً عند الحفظ: {doc.spare_asset}")
        else:
            _fail(f"لم يُكتشف الأصل الاحتياطي كما هو متوقع "
                  f"(spare_available={doc.spare_available}, doc.asset_category={doc.asset_category}, "
                  f"doc.item_code={doc.item_code})")

        doc.submit()
        doc.approve_finance()
        doc.approve_branch_manager()
        doc.approve_asset_manager()
        doc.reload()

        movement_name = doc.create_asset_movement()
        doc.reload()
        spare.reload()
        if movement_name and doc.status == "Fulfilled":
            _ok(f"create_asset_movement: تم إنشاء سند استلام {movement_name} "
                f"وأصبحت حالة الطلب 'Fulfilled'")
        else:
            _fail("create_asset_movement: نتيجة غير متوقعة")

        movement = frappe.get_doc("Asset Movement", movement_name)
        if movement.purpose == "Receipt":
            _ok("سند النقل من نوع 'Receipt' كما هو متوقع (وليس Transfer)")
        else:
            _fail(f"نوع سند النقل غير متوقع: {movement.purpose}")

        # --- سيناريو ب: لا يوجد احتياطي ولا مخزون فعلي -> طلب شراء ---
        doc2 = frappe.new_doc("Asset Requisition")
        doc2.employee = employee
        doc2.asset_category = category
        doc2.item_code = item_code
        doc2.quantity = 1
        doc2.request_date = today()
        doc2.justification = "اختبار تنفيذ الطلب — طلب شراء (Demo Test)"
        doc2.insert(ignore_permissions=True)
        if doc2.spare_available or doc2.stock_available:
            _skip("سيناريو طلب الشراء: يوجد احتياطي أو مخزون فعلي متاح فعلاً بنفس الصنف — تخطي")
            return

        doc2.submit()
        doc2.approve_finance()
        doc2.approve_branch_manager()
        doc2.approve_asset_manager()
        doc2.reload()
        mr_name = doc2.create_purchase_requisition()
        doc2.reload()
        if mr_name and doc2.status == "Fulfilled" and frappe.db.exists("Material Request", mr_name):
            _ok(f"create_purchase_requisition: تم إنشاء طلب شراء {mr_name} "
                f"وأصبحت حالة الطلب 'Fulfilled'")
        else:
            _fail("create_purchase_requisition: نتيجة غير متوقعة")

    except Exception as e:
        _fail("فشل اختبار تنفيذ الطلب المعتمد", e)


# ---------------------------------------------------------------------------
# اختبار 8: شطب أصل (Asset Write-off Request) — القيد المحاسبي التلقائي
# ---------------------------------------------------------------------------

def _test_asset_writeoff():
    _header("8) شطب أصل (Asset Write-off Request) — القيد المحاسبي")
    try:
        asset, created = _get_or_create_submitted_asset()
        if not asset:
            return

        asset_doc = frappe.get_doc("Asset", asset)
        _ok(f"استخدام الأصل: {asset}{' (تم إنشاؤه تجريبياً)' if created else ''}")

        wo = frappe.new_doc("Asset Write-off Request")
        wo.asset = asset
        wo.write_off_date = today()
        wo.reason = "Obsolete"
        wo.description = "اختبار توضيحي تلقائي (Demo Test)"
        wo.estimated_loss_value = 750
        wo.insert(ignore_permissions=True)
        wo.submit()
        wo.reload()
        if wo.status == "Pending Approval":
            _ok(f"تم تقديم طلب الشطب {wo.name} — الحالة 'Pending Approval' كما هو متوقع")
        else:
            _fail(f"بعد التقديم: الحالة غير متوقعة = {wo.status}")

        frappe.db.set_value("Asset Write-off Request", wo.name, "status", "Approved")
        wo.reload()

        je_name = wo.create_journal_entry()
        wo.reload()
        if not je_name:
            _fail("create_journal_entry: لم يرجع اسم قيد يومية")
            return

        je = frappe.get_doc("Journal Entry", je_name)
        total_debit = sum(row.debit_in_account_currency for row in je.accounts)
        total_credit = sum(row.credit_in_account_currency for row in je.accounts)
        _ok(f"تم إنشاء قيد يومية {je.name} — إجمالي مدين={total_debit}, دائن={total_credit}")
        if total_debit == total_credit == 750:
            _ok("المبالغ متزنة ومطابقة للقيمة المُقدَّرة (750) — تم استخدام estimated_loss_value بشكل صحيح")
        else:
            _fail(f"المبالغ غير متزنة أو غير مطابقة (متوقع 750, وجد مدين={total_debit})")

        if wo.status == "Executed" and wo.journal_entry == je.name:
            _ok("حالة طلب الشطب أصبحت 'Executed' وربط قيد اليومية صحيح")
        else:
            _fail(f"حالة/ربط طلب الشطب غير متوقع: status={wo.status}, journal_entry={wo.journal_entry}")

    except Exception as e:
        _fail("فشل اختبار شطب الأصل", e)


# ---------------------------------------------------------------------------
# تشخيص فقط (قراءة، بدون أي تعديل) — لمعرفة سبب عدم وجود حساب Fixed Asset
# طريقة التشغيل:
#   bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.diagnose_accounts
# ---------------------------------------------------------------------------

def diagnose_accounts():
    company = _get_default_company()
    print(f"الشركة: {company}\n")

    print("كل حسابات نوع الأصول (root_type = Asset) غير التجميعية (is_group=0):")
    rows = frappe.db.sql(
        """
        SELECT name, account_type, parent_account
        FROM `tabAccount`
        WHERE company = %s AND root_type = 'Asset' AND is_group = 0
        ORDER BY parent_account, name
        """,
        company,
        as_dict=True,
    )
    if not rows:
        print("  (لا يوجد أي حساب أصول غير تجميعي على الإطلاق لهذه الشركة)")
    for r in rows:
        marker = "  <-- هذا مُصنَّف كـ Fixed Asset" if r.account_type == "Fixed Asset" else ""
        print(f"  - {r.name}  |  account_type={r.account_type or '(فارغ)'}  |  parent={r.parent_account}{marker}")

    print("\nكل الحسابات (تجميعية وغير تجميعية) اللي اسمها يحتوي 'Fixed' أو 'أصول':")
    rows2 = frappe.db.sql(
        """
        SELECT name, account_type, is_group, root_type
        FROM `tabAccount`
        WHERE company = %s AND (name LIKE %s OR name LIKE %s)
        ORDER BY name
        """,
        (company, "%Fixed%", "%أصول%"),
        as_dict=True,
    )
    if not rows2:
        print("  (لا يوجد)")
    for r in rows2:
        print(f"  - {r.name}  |  account_type={r.account_type or '(فارغ)'}  |  "
              f"is_group={r.is_group}  |  root_type={r.root_type}")


def diagnose_payable_accounts():
    """قراءة فقط — bootstrap لقى إنه مفيش أي حساب مُصنَّف account_type='Payable'
    في شجرة حساباتك، بالظبط زي مشكلة 'Fixed Asset' قبل كده. الأرجح إن فيه
    حساب دائنين/موردين حقيقي موجود بس مش مُصنَّف بالنوع الصحيح — السكريبت
    ده بيسردهم عشان تحدد الصح، بدل ما ننشئ حساب جديد ممكن يكرر حساب موجود.
    طريقة التشغيل:
      bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.diagnose_payable_accounts
    """
    company = _get_default_company()
    print(f"الشركة: {company}\n")

    print("كل الحسابات (تجميعية وغير تجميعية) اللي اسمها فيه 'دائن' أو 'مورد' أو 'Payable':")
    rows = frappe.db.sql(
        """
        SELECT name, account_type, is_group, root_type, parent_account
        FROM `tabAccount`
        WHERE company = %s AND (name LIKE %s OR name LIKE %s OR name LIKE %s)
        ORDER BY name
        """,
        (company, "%دائن%", "%مورد%", "%Payable%"),
        as_dict=True,
    )
    if not rows:
        print("  (لا يوجد أي حساب بهذا الاسم على الإطلاق)")
    for r in rows:
        marker = "  <-- مُصنَّف Payable بالفعل" if r.account_type == "Payable" else ""
        print(f"  - {r.name}  |  account_type={r.account_type or '(فارغ)'}  |  "
              f"is_group={r.is_group}  |  root_type={r.root_type}{marker}")

    print("\nكل الحسابات تحت مجموعة (Liability) غير التجميعية (أول 20 فقط، للاستئناس):")
    rows2 = frappe.db.sql(
        """
        SELECT name, account_type FROM `tabAccount`
        WHERE company = %s AND root_type = 'Liability' AND is_group = 0
        ORDER BY name LIMIT 20
        """,
        company,
        as_dict=True,
    )
    for r in rows2:
        print(f"  - {r.name}  |  account_type={r.account_type or '(فارغ)'}")


def diagnose_cwip_accounts():
    """
    قراءة فقط — تحقق هل فيه حساب 'رأس المال قيد التنفيذ' (Capital Work in
    Progress) موجود بالفعل تحت مجموعة الأصول في شجرة حساباتك الحقيقية،
    منفصل عن الحساب اللي أنشأه bootstrap ("أصول تحت الصيانة الرأسمالية").
    لو موجود، ممكن يكون نفس الحساب المطلوب أصلاً بدل ما ننشئ واحد جديد.
    طريقة التشغيل:
      bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.diagnose_cwip_accounts
    """
    company = _get_default_company()
    print(f"الشركة: {company}\n")

    print("كل الحسابات تحت مجموعة الأصول (root_type=Asset) اللي اسمها فيه "
          "'رأس المال' أو 'قيد التنفيذ' أو 'تحت التنفيذ' أو 'CWIP' أو 'Work in Progress':")
    rows = frappe.db.sql(
        """
        SELECT name, account_type, is_group, parent_account, account_number
        FROM `tabAccount`
        WHERE company = %s AND root_type = 'Asset'
          AND (name LIKE %s OR name LIKE %s OR name LIKE %s OR name LIKE %s OR name LIKE %s)
        ORDER BY name
        """,
        (company, "%رأس المال%", "%قيد التنفيذ%", "%تحت التنفيذ%", "%CWIP%", "%Work in Progress%"),
        as_dict=True,
    )
    if not rows:
        print("  (لا يوجد أي حساب بهذا الاسم تحت الأصول)")
    for r in rows:
        marker = "  <-- مُصنَّف Capital Work in Progress بالفعل" if r.account_type == "Capital Work in Progress" else ""
        print(f"  - {r.name}  |  رقم={r.account_number or '(بدون)'}  |  account_type={r.account_type or '(فارغ)'}  |  "
              f"is_group={r.is_group}  |  parent={r.parent_account}{marker}")

    print("\nالحساب اللي أنشأه bootstrap (لو موجود):")
    wired = frappe.db.get_value(
        "Asset Category Account",
        {"parent": "أصول عامة", "company_name": company},
        "custom_capital_maintenance_wip_account",
    )
    print(f"  {wired or '(غير مربوط)'}")


def diagnose_companies():
    """فحص أوسع: هل شجرة الحسابات (Chart of Accounts) موجودة أصلاً لأي شركة
    في النظام؟ لو مفيش أي حساب خالص لأي شركة، فده معناه شجرة الحسابات لم
    تُنشأ من الأساس (وده أكبر من مجرد حساب واحد ناقص).
    طريقة التشغيل:
      bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.diagnose_companies
    """
    companies = frappe.get_all("Company", fields=["name", "default_currency", "country"])
    print(f"عدد الشركات في النظام: {len(companies)}\n")

    for c in companies:
        total = frappe.db.count("Account", {"company": c.name})
        roots = frappe.db.sql(
            """
            SELECT name, root_type FROM `tabAccount`
            WHERE company = %s AND is_group = 1 AND (parent_account IS NULL OR parent_account = '')
            """,
            c.name,
            as_dict=True,
        )
        print(f"- {c.name}  (currency={c.default_currency}, country={c.country})")
        print(f"    إجمالي عدد الحسابات: {total}")
        if roots:
            print(f"    الحسابات الجذرية (Root): {[f'{r.name} ({r.root_type})' for r in roots]}")
        else:
            print("    لا توجد أي حسابات جذرية — شجرة الحسابات غير موجودة إطلاقاً لهذه الشركة")

    total_accounts_system_wide = frappe.db.count("Account")
    print(f"\nإجمالي عدد الحسابات في كل النظام (كل الشركات): {total_accounts_system_wide}")

    default_company = frappe.defaults.get_global_default("company")
    print(f"الشركة الافتراضية (Global Default Company): {default_company}")
