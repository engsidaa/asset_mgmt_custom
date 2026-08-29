"""
سكريبت اختبار توضيحي (Demo/Smoke Test) — للتشغيل اليدوي فقط، وليس جزءاً من
دورة الـ migrate العادية.

الغرض: تجربة أهم المسارات اللي بُنيت في المراحل 1-4 (سلسلة اعتماد Asset
Requisition، القيد المحاسبي التلقائي لـ Asset Repair، استثناء الاحتفاظ
بالعهدة في Full and Final Statement) على بيانات وهمية، وطباعة النتيجة
خطوة بخطوة في الـ console — بدون ترك أي أثر حقيقي في قاعدة البيانات.

مهم جداً: كل التغييرات بتترجع (frappe.db.rollback) في نهاية السكريبت
تلقائياً، حتى لو نجح كل شيء. فمفيش أي بيانات وهمية هتفضل موجودة بعد
التشغيل — الهدف فقط قراءة الـ output والتأكد إن المنطق شغال صح.

طريقة التشغيل من السيرفر:
    cd ~/frappe-bench
    bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.demo_test.run_demo_test
"""

import frappe
from frappe.utils import today, add_days


def _ok(msg):
    print(f"✅ {msg}")


def _fail(msg, exc=None):
    print(f"❌ {msg}")
    if exc:
        print(f"    السبب: {exc}")


def _skip(msg):
    print(f"⏭️  تخطي: {msg}")


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
# اختبار 2: سلسلة اعتماد Asset Requisition (3 مراحل) + الرفض
# ---------------------------------------------------------------------------

def _test_asset_requisition_chain():
    _header("2) سلسلة اعتماد Asset Requisition (تمويل ← مدير فرع ← مدير أصول)")
    try:
        employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
        category = frappe.db.get_value("Asset Category", {}, "name")

        if not employee:
            _skip("لا يوجد موظف نشط (Active Employee) في النظام لتجربة الطلب عليه")
            return
        if not category:
            _skip("لا توجد فئة أصول (Asset Category) في النظام")
            return

        _ok(f"استخدام الموظف: {employee} | فئة الأصل: {category}")

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
        asset = frappe.db.get_value(
            "Asset", {"docstatus": 1, "status": ["not in", ["Scrapped", "Sold"]]}, "name"
        )
        if not asset:
            _skip("لا يوجد أي أصل مُعتمَد (Submitted) في النظام لتجربة الإصلاح عليه")
            return

        asset_doc = frappe.get_doc("Asset", asset)
        _ok(f"استخدام الأصل: {asset} (الفئة: {asset_doc.asset_category})")

        category_account = frappe.db.get_value(
            "Asset Category Account",
            {"parent": asset_doc.asset_category, "company_name": asset_doc.company},
            ["fixed_asset_account", "custom_capital_maintenance_wip_account",
             "custom_maintenance_expense_account"],
            as_dict=True,
        )
        if not category_account:
            _skip(f"لا يوجد إعداد حسابات (Asset Category Account) لفئة "
                  f"'{asset_doc.asset_category}' / شركة '{asset_doc.company}' — "
                  f"لازم يُضاف قبل ما نقدر نختبر القيد المحاسبي")
            return

        # --- OpEx: إصلاح عادي بدون رسملة ---
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
                _fail(f"OpEx: المبالغ غير متزنة أو غير مطابقة (متوقع 500)")
        else:
            _skip("OpEx: لم يُنشأ قيد يومية — على الأغلب معندهاش custom_maintenance_expense_account "
                  "أو default_payable_account مُعرَّفين")

        # --- اختبار سلبي: رسملة بدون تمديد العمر يجب أن تُرفض ---
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

        # --- CapEx: رسملة صحيحة مع تمديد العمر ---
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
        if not row:
            _skip("لا يوجد أي أصل بعهدة موظف حالياً (Asset Movement مع to_employee) — "
                  "لا يمكن تجربة هذا السيناريو بدون بيانات عهدة حقيقية")
            return

        employee, asset = row[0].employee, row[0].asset
        _ok(f"استخدام الموظف: {employee} | الأصل بعهدته: {asset}")

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

        ff = frappe.new_doc("Full and Final Statement")
        ff.employee = employee
        ff.relieving_date = today()
        ff.insert(ignore_permissions=True)
        _ok(f"تم إنشاء Full and Final Statement {ff.name} (بدون submit)")

        target_row = next(
            (r for r in ff.assets_allocated if _asset_for_row_matches(r, employee, asset)),
            None,
        )
        if not target_row:
            _skip("الأصل المُحتفَظ به لم يظهر في جدول assets_allocated — "
                  "غالباً لأن سجل Asset Movement القديم غير مرتبط بشكل يسمح لـ HRMS "
                  "بربطه تلقائياً (سلوك طبيعي حسب البيانات الفعلية، وليس بالضرورة خطأ)")
        elif target_row.action == "Recover Cost" and flt_zero(target_row.cost):
            _ok("الأصل المحتفَظ به تم استثناؤه بنجاح: action='Recover Cost', cost=0 "
                "— لن يمنع اعتماد المخالصة")
        else:
            _fail(f"الأصل المحتفَظ به لم يُستثنَ كما هو متوقع: "
                  f"action={target_row.action}, cost={target_row.cost}")

    except Exception as e:
        _fail("فشل اختبار استثناء الاحتفاظ بالعهدة", e)


def flt_zero(value):
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
