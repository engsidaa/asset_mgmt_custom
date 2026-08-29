"""
تجهيز الإعداد الأساسي الحقيقي (Chart of Accounts + Asset Category) —
للتشغيل اليدوي مرة واحدة فقط عندما يكون النظام فاضياً تماماً من بيانات
الأصول (كما هو الحال حالياً في e-u40.hosetia.com).

خلافاً لـ demo_test.py، هذا السكريبت **لا يعمل rollback** — البيانات
اللي بيُنشئها إعداد أساسي حقيقي ودائم (حسابات + فئة أصل)، مش بيانات
تجريبية مؤقتة. مفيش أي بيانات وهمية (أصول، طلبات، إلخ) بتتعمل هنا —
فقط الإعداد اللي وحدة الأصول محتاجاه عشان تشتغل، وبعدها تقدر تدخل أصولك
الحقيقية من الواجهة (UI) عادي.

آمن للتشغيل أكثر من مرة: كل خطوة تتأكد أولاً هل الحساب/الفئة موجودة قبل
ما تنشئ حاجة جديدة، وبتصحح أي ربط خاطئ حصل في تشغيل سابق (انظر تعليق
_find_or_create_leaf_account أدناه لتفاصيل خطأين تم اكتشافهما وتصحيحهما:
حساب أُنشئ تحت مجموعة "مجمع إهلاك" بالغلط، وحساب آخر أُعيد استخدامه فقط
لأن رقمه (110902) تصادف مع حساب حقيقي غير مرتبط إطلاقاً بالغرض المطلوب).

طريقة التشغيل من السيرفر:
    cd ~/frappe-bench
    bench --site e-u40.hosetia.com execute asset_mgmt_custom.setup.bootstrap_demo_master_data.run
"""

import frappe


def _step(msg):
    print(f"\n→ {msg}")


def _ok(msg):
    print(f"  ✅ {msg}")


def _warn(msg):
    print(f"  ⚠️  {msg}")


def run():
    print("#" * 70)
    print("# تجهيز الإعداد الأساسي لوحدة الأصول (حسابات حقيقية + فئة أصل واحدة)")
    print("#" * 70)

    company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
    if not company:
        _warn("لا توجد أي شركة (Company) في النظام — توقف.")
        return
    print(f"\nالشركة: {company}")

    fixed_assets_group = _find_or_create_fixed_assets_group(company)
    if not fixed_assets_group:
        return

    fixed_asset_account = _find_or_create_leaf_account(
        company,
        parent=fixed_assets_group,
        account_name="أصول ثابتة عامة",
        account_type="Fixed Asset",
    )

    # رقم 110902 كان مطلوباً في الأصل لهذا الحساب، لكنه مُستخدَم بالفعل
    # لحساب حقيقي آخر غير مرتبط ("اصول متداولة متنوعة اخرى - مستوى 4").
    # بناءً على قرار المستخدم: يُنشأ بدون رقم محدد — النظام (autoname)
    # يعطيه رقماً تلقائياً ضمن شجرة الحسابات، ويمكن تعديله لاحقاً من الواجهة.
    wip_account = _find_or_create_leaf_account(
        company,
        parent=fixed_assets_group,
        account_name="أصول تحت الصيانة الرأسمالية (حساب وساطة)",
        account_type="Capital Work in Progress",
    )

    expense_group = _find_expense_group(company)
    maintenance_expense_account = None
    if expense_group:
        maintenance_expense_account = _find_or_create_leaf_account(
            company,
            parent=expense_group,
            account_name="مصروف صيانة الأصول",
            account_type="Indirect Expense",
        )
    else:
        _warn("لم يتم العثور على مجموعة مصروفات (Expense) — تم تخطي حساب مصروف الصيانة")

    _ensure_default_payable_account(company)

    _step("إنشاء/تحديث فئة أصل واحدة تربط الحسابات السابقة")
    category_name = "أصول عامة"
    if frappe.db.exists("Asset Category", category_name):
        cat = frappe.get_doc("Asset Category", category_name)
        _ok(f"الفئة '{category_name}' موجودة بالفعل — سيتم تحديث حسابات الشركة عليها فقط")
    else:
        cat = frappe.new_doc("Asset Category")
        cat.asset_category_name = category_name

    row = None
    for r in cat.get("accounts", []):
        if r.company_name == company:
            row = r
            break
    if not row:
        row = cat.append("accounts", {})
        row.company_name = company

    # مهم: نضبط القيمة صراحة دايماً (حتى لو None) بدل الشرط الجزئي القديم
    # (if x: row.field = x) — عشان لو تشغيل سابق ربط حساب غلط، التشغيل ده
    # يصححه/يمسحه بدل ما يسيبه زي ما هو.
    row.fixed_asset_account = fixed_asset_account
    row.custom_capital_maintenance_wip_account = wip_account
    row.custom_maintenance_expense_account = maintenance_expense_account

    if cat.is_new():
        cat.insert(ignore_permissions=True)
    else:
        cat.save(ignore_permissions=True)
    frappe.db.commit()
    _ok(f"فئة الأصل جاهزة: {cat.name}")

    print("\n" + "#" * 70)
    print("# تم — ملخص ما تم إنشاؤه/التأكد منه:")
    print("#" * 70)
    print(f"  فئة الأصل: {cat.name}")
    print(f"  حساب الأصل الثابت (Fixed Asset): {fixed_asset_account or '(لم يُنشأ — راجع التحذيرات أعلاه)'}")
    print(f"  حساب الوساطة (Capital Work in Progress): {wip_account or '(لم يُنشأ — راجع التحذيرات أعلاه)'}")
    print(f"  حساب مصروف الصيانة (Indirect Expense): {maintenance_expense_account or '(لم يُنشأ)'}")
    print("\nراجع هذه الحسابات في شجرة الحسابات (Chart of Accounts) وعدّل الأسماء/الأرقام")
    print("لو حابب تناسب ترقيمك المحاسبي الفعلي — دي بداية جاهزة للعمل، مش نهائية بالضرورة.")
    print("\nبعد كده تقدر تشغّل demo_test.run_demo_test تاني وهيكمل الاختبارات الفعلية بدل التخطي.")


def _get_asset_root(company):
    """SQL IN never matches NULL, so this must be raw SQL (a plain ORM
    get_value with parent_account in ["", None] silently never matches
    the real root row where parent_account is NULL)."""
    row = frappe.db.sql(
        """
        SELECT name FROM `tabAccount`
        WHERE company = %s AND is_group = 1 AND root_type = 'Asset'
          AND (parent_account IS NULL OR parent_account = '')
        LIMIT 1
        """,
        company,
    )
    return row[0][0] if row else None


def _find_or_create_fixed_assets_group(company):
    """يدوّر على مجموعة تمثل 'الأصول الثابتة نفسها' (تكلفة الاقتناء) —
    وليس 'مجمع إهلاك الأصول الثابتة' (Accumulated Depreciation)، وهي
    مجموعة مقابلة (contra-asset) مختلفة تماماً رغم إن اسمها بيحتوي نفس
    الكلمات. أول تشغيل وقع في هذا الخطأ بالظبط: لاقى '120108 - مجمع اهلاك
    الاصول الثابتة' عن طريق تطابق '%ثابتة%' وحطّ الحساب الجديد تحتها،
    وهو غلط محاسبياً (حساب أصل تحت مجموعة مقابلة/دائنة)."""
    _step("البحث عن مجموعة 'الأصول الثابتة' (Fixed Assets) في شجرة الحسابات")

    exclude_keywords = ["اهلاك", "إهلاك", "مجمع", "Depreciation", "Accumulated"]

    for pattern in ["%Fixed Asset%", "%ثابتة%"]:
        candidates = frappe.db.get_all(
            "Account",
            filters={"company": company, "is_group": 1, "root_type": "Asset", "account_name": ["like", pattern]},
            fields=["name", "account_name"],
        )
        for c in candidates:
            if any(k in c.account_name for k in exclude_keywords):
                continue
            _ok(f"موجودة بالفعل: {c.name}")
            return c.name

    asset_root = _get_asset_root(company)
    if not asset_root:
        _warn("لا يوجد حتى جذر أصول (Asset root) في شجرة الحسابات — شجرة الحسابات نفسها غير مُعدَّة. توقف.")
        return None

    children = frappe.db.sql(
        """
        SELECT name, is_group FROM `tabAccount`
        WHERE company = %s AND parent_account = %s
        ORDER BY name
        """,
        (company, asset_root),
        as_dict=True,
    )
    _warn(f"لم يتم العثور على مجموعة 'أصول ثابتة' حقيقية (غير مجمع الإهلاك) تلقائياً تحت الجذر "
          f"'{asset_root}'. هذه شجرة حسابات حقيقية بها مئات الحسابات بالفعل — لن يتم إنشاء مجموعة "
          f"جديدة تلقائياً تفادياً لتكرار مجموعة موجودة باسم مختلف. الحسابات/المجموعات الموجودة "
          f"مباشرة تحت جذر الأصول هي:")
    for c in children:
        print(f"      - {c.name}  ({'مجموعة' if c.is_group else 'حساب فرعي'})")
    print("\n  راجع القائمة دي وقولّي أنهي حساب/مجموعة هو المقصود بـ 'الأصول الثابتة' فعلياً،")
    print("  أو لو مفيش أي حاجة مناسبة، قولّي أنشئ مجموعة جديدة باسم محدد منك.")
    return None


def _ensure_default_payable_account(company):
    """
    الإصلاح غير الرأسمالي (OpEx) بدون فاتورة شراء مرتبطة بيترحّل لحساب
    الدائنين الافتراضي للشركة (Company.default_payable_account) — لو مش
    معرَّف، القيد المحاسبي هيفشل مهما كانت باقي الإعدادات صحيحة. هذا
    إعداد على مستوى الشركة نفسها (مش على فئة الأصل) فبنتأكد منه مرة واحدة
    هنا. لا نغيّر القيمة أبداً لو كانت معرَّفة بالفعل — فقط نملأ الفراغ.
    """
    _step("التأكد من 'Default Payable Account' على مستوى الشركة")

    current = frappe.db.get_value("Company", company, "default_payable_account")
    if current:
        _ok(f"مُعرَّف بالفعل: {current}")
        return

    payable = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Payable", "is_group": 0}, "name"
    )
    if not payable:
        _warn("لا يوجد أي حساب من نوع 'Payable' في شجرة الحسابات — لن يتم ضبط شيء. "
              "إصلاحات OpEx بدون فاتورة شراء ستفشل حتى يُعرَّف هذا الحساب يدوياً.")
        return

    frappe.db.set_value("Company", company, "default_payable_account", payable)
    frappe.db.commit()
    _ok(f"تم ضبط 'Default Payable Account' = {payable}")


def _find_expense_group(company):
    for pattern in ["%Indirect Expense%", "%غير مباشرة%", "%مصروفات%", "%نفقات%"]:
        group = frappe.db.get_value(
            "Account",
            {"company": company, "is_group": 1, "root_type": "Expense", "account_name": ["like", pattern]},
            "name",
        )
        if group:
            return group
    row = frappe.db.sql(
        """
        SELECT name FROM `tabAccount`
        WHERE company = %s AND is_group = 1 AND root_type = 'Expense'
          AND (parent_account IS NULL OR parent_account = '')
        LIMIT 1
        """,
        company,
    )
    return row[0][0] if row else None


def _find_or_create_leaf_account(company, parent, account_name, account_type, account_number=None):
    """
    ملاحظتان مهمتان اتصلّحوا هنا بعد أول تشغيل:

    1. لو لقينا حساب من نفس النوع (account_type) موجود بالفعل، بنستخدمه —
       لكن لو والده (parent_account) مش نفس المجموعة الصحيحة اللي حددناها
       (fixed_assets_group)، بننقله لها بدل ما نسيبه في مكانه الغلط.

    2. رقم الحساب (account_number) وحده مش كافي لاعتبار حساب "موجود
       بالفعل ومناسب" — أول تشغيل لقى حساب حقيقي غير مرتبط تماماً
       ('اصول متداولة متنوعة اخرى') بس رقمه اتصادف 110902، واستخدمه غلط.
       دلوقتي: لو الرقم مستخدم لحساب من نوع مختلف تماماً، نعتبرها تعارض
       حقيقي ونتوقف — مش نستخدمه ومش ننشئ حساب جديد بنفس الرقم (هيفشل
       أصلاً لأن رقم الحساب لازم يكون فريد).
    """
    _step(f"التأكد من حساب '{account_name}' (نوع: {account_type})")

    existing = frappe.db.get_value(
        "Account", {"company": company, "account_type": account_type, "is_group": 0},
        ["name", "parent_account"], as_dict=True,
    )
    if existing:
        if existing.parent_account != parent:
            _warn(f"حساب '{existing.name}' من نفس النوع موجود، لكنه تحت مجموعة غير صحيحة "
                  f"('{existing.parent_account}') — سيتم نقله إلى '{parent}'")
            doc = frappe.get_doc("Account", existing.name)
            doc.parent_account = parent
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            _ok(f"تم نقل الحساب إلى المجموعة الصحيحة: {doc.name}")
        else:
            _ok(f"موجود بالفعل حساب من نفس النوع وتحت المجموعة الصحيحة: {existing.name}")
        return existing.name

    if account_number:
        conflict = frappe.db.get_value(
            "Account", {"company": company, "account_number": account_number},
            ["name", "account_type"], as_dict=True,
        )
        if conflict:
            _warn(f"رقم الحساب {account_number} مستخدم بالفعل لحساب مختلف تمامًا عن الغرض المطلوب: "
                  f"'{conflict.name}' (نوعه: {conflict.account_type or 'غير محدد'}, "
                  f"والمطلوب: {account_type}) — لن يُستخدم هذا الحساب. اختر رقم حساب آخر غير مستخدم.")
            return None

    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": account_name,
        "parent_account": parent,
        "company": company,
        "is_group": 0,
        "account_type": account_type,
        "account_number": account_number,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _ok(f"تم إنشاء حساب جديد: {doc.name}")
    return doc.name
