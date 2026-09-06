# CLAUDE.md — دليل معماري لتطبيق `asset_mgmt_custom`

هذا الملف مرجع معماري حيّ لأي عمل مستقبلي على هذا التطبيق (بواسطة Claude
أو أي مطوّر آخر). يوثِّق القرارات المعمارية الصارمة المتفق عليها، ويُحدَّث
مع كل مرحلة تطوير كبيرة — وليس مجرد سجل تاريخي.

## السياق

`asset_mgmt_custom` تطبيق Frappe/ERPNext v15 مخصص لشركة **كويت الغذاء**
(سلسلة مطاعم/أغذية، SAR) — يوسِّع موديول Assets/Maintenance القياسي في
ERPNext ليغطي إدارة أصول ومرافق وصيانة على مستوى مؤسسي (EAM/CMMS)، متوافق
مع فروع متعددة، مورِّدي صيانة خارجيين، ومديري فروع (Branch Manager).

بيئة النشر: `~/frappe-bench/apps/asset_mgmt_custom` على مواقع إنتاج فعلية
(`e-u39.hosetia.com`, `e-u40.hosetia.com`). **لا يوجد وصول مباشر لقاعدة
البيانات/السيرفر من جلسات التطوير** — فقط `git commit` + `push`؛ المستخدم
هو من يُنفِّذ `bench migrate`/`bench restart` فعلياً.

---

## المحددات المعمارية الصارمة (غير قابلة للتفاوض)

### 1. عدم المساس بالنواة نهائياً (Zero Core Alterations)
- **يُمنع تماماً** تعديل أي ملف داخل تطبيقي `frappe` أو `erpnext` نفسيهما.
  هذان مرجعان للقراءة فقط (موجودان محلياً في بيئة بعض جلسات التطوير
  لغرض التحقق من السلوك الحقيقي للـ Core قبل الاعتماد عليه — **وليس
  للتعديل إطلاقاً**).
- **يُمنع الـ Monkey Patching** لأي كلاس أو دالة قياسية. البديل الوحيد
  المعتمد: `doc_events` في `hooks.py` (hooks على دورة حياة المستند:
  `validate`, `on_submit`, `on_cancel`, `on_update_after_submit`, ...)
  تستدعي دوال في `asset_mgmt_custom/overrides/<doctype>.py`.
- الهدف: **Upgrade-Safe 100%** — ترقية `frappe`/`erpnext` لا يجب أبداً أن
  تكسر هذا التطبيق أو العكس.

### 2. إدارة الهياكل عبر Fixtures فقط
كل حقل مُضاف على مستند قياسي (`Asset`, `Branch`, `Stock Entry`,
`Cost Center`, `Journal Entry`, ...) يُدار حصراً عبر:
- `fixtures/custom_field.json` — الحقول المخصصة.
- `fixtures/property_setter.json` — تعديل خصائص حقول قياسية (مثال:
  `reqd`, `options`) دون المساس بملف الـ DocType الأصلي.
- `fixtures/custom_docperm.json` — صلاحيات أدوار جديدة على مستندات قياسية.
- كل ما سبق مُدرج في `hooks.py`'s `fixtures = [...]` بفلتر دقيق (لا
  تصدير عشوائي لكل الحقول المخصصة في قاعدة البيانات — فقط ما يخص هذا
  التطبيق تحديداً).

### 3. الهرمية المكانية والمالية الإجبارية
```
Company -> Branch -> Location / Warehouse -> Asset
```
كل أصل، وكل أمر عمل، وكل حركة مخزنية **يجب** أن يرث مركز التكلفة
(`Cost Center`) والفرع (`Branch`) تلقائياً من هذه الهرمية عبر `doc_events`
(`validate`/`before_insert`) — **وليس إدخالاً يدوياً أبداً**. أي حقل
Cost Center/Branch جديد يُضاف كـ Fetch Field أو يُملأ عبر كود، لا يُترك
فارغاً ينتظر المستخدم.

### 4. المعالجة الخلفية غير المتزامنة
أي عملية حسابية تراكمية أو مكلفة (مؤشرات موثوقية MTBF/MTTR، تكلفة الملكية
TCO، مؤشر صحة الأصل AHI، إعادة حساب جماعي) **يجب** أن تُرحَّل عبر
`frappe.enqueue(queue="default"|"long", ...)` — لا تُنفَّذ أبداً بشكل
متزامن داخل طلب واجهة المستخدم (`validate`/`on_submit` مباشرة). الاستثناء
الوحيد: عمليات فورية صغيرة الحجم (تحديث حقل واحد، فحص شرط بسيط).

### 5. لا تكرار في البنية — تحقق قبل الإنشاء
هذا التطبيق يحتوي بالفعل على عشرات الـ DocTypes المُنشأة مسبقاً
(انظر `asset_mgmt_custom/asset_mgmt_custom/doctype/`) تغطي مساحة واسعة
من دورة حياة الأصول (Requisition → Booking → Checkout → Repair →
Maintenance → Disposal → Write-Off، بالإضافة إلى Lease، Warranty، SLA،
Vendor Contract، Energy/Fuel Log، Safety Inspection، إلخ). **قبل إنشاء
أي DocType جديد، تحقق أولاً أنه غير موجود بالفعل تحت اسم مختلف** — الكثير
من المتطلبات المعمارية الكبيرة (SAP/Maximo-style EAM) هي في الغالب مسألة
**بناء منطق الأعمال/التكامل المالي الناقص فوق سقالة (scaffold) موجودة
بالفعل**، وليس بناء بنية جديدة من الصفر.

---

## تنظيم الملفات

| المسار | الغرض |
|---|---|
| `asset_mgmt_custom/hooks.py`, `tasks.py` | نقطة التجميع: `doc_events`, `scheduler_events`, `fixtures`, `permission_query_conditions` |
| `asset_mgmt_custom/overrides/<doctype>.py` | هوكات دورة حياة مستندات **قياسية** (Asset, Asset Movement, Asset Repair, Branch, Full and Final Statement) |
| `asset_mgmt_custom/events/` | (جديد — طبقة توسعية) هوكات دورة حياة أثقل/أعمق تخص عدة مستندات معاً (تكامل مالي/مخزني عابر للـ doctypes)، فصلاً عن `overrides/` البسيطة |
| `asset_mgmt_custom/api/` | نقاط API مستقلة قابلة للاستدعاء (`branch_manager.py` — بوابة مدير الفرع؛ `v1/mobile.py`, `v1/telemetry.py` — واجهات Headless لتطبيق Flutter وأجهزة IoT مستقبلاً) |
| `asset_mgmt_custom/setup/after_migrate.py` | مهام تُنفَّذ بعد مزامنة الـ fixtures (وليس قبلها) عند `bench migrate` |
| `asset_mgmt_custom/notifications.py` | تنبيهات حرجة (WhatsApp/SMS-ready عبر Webhook) |
| `asset_mgmt_custom/public/js/wizard_framework.js` + `page/*_wizard/` | إطار عمل صفحات الويزارد (خطوة بخطوة) ومثيلاتها |
| `<repo_root>/<app_pkg>/` (مستوى ٢) | `overrides/`, `setup/`, `api/`, `events/`, `www/`, `patches/`, `hooks.py`, `tasks.py` |
| `<repo_root>/<app_pkg>/<app_pkg>/` (مستوى ٣) | `doctype/`, `report/`, `page/`, `print_format/` (تُطابق Module Def: "Asset Mgmt Custom") |

**ملاحظة مهمة موثَّقة سابقاً (تكرر الإشارة إليها لتجنب تكرار الخطأ):**
مسار `api/` (ومثله `events/`) يقع في **مستوى ٢** (بجانب `overrides/`)،
وليس داخل مجلد الموديول في مستوى ٣ — تم اكتشاف هذا الخطأ وتصحيحه فعلياً
مرة سابقاً.

---

## سير العمل المعتمد لكل تعديل

1. تحقق أولاً من السلوك الحقيقي في Frappe/ERPNext Core (القراءة فقط من
   `/home/user/frappe`, `/home/user/erpnext`) قبل افتراض أي API أو حقل.
2. تحقق من عدم وجود DocType/حقل/منطق مشابه بالفعل في هذا التطبيق.
3. عدِّل، ثم تحقق التركيب:
   - JSON: `python3 -c "import json; json.load(open('FILE'))"`
   - Python: `python3 -m py_compile FILE`
   - JS: `node --check FILE`
4. `git add` → `git commit` (رسالة تشرح **لماذا**، ليس فقط ماذا) → `git push origin claude/asl-aliye-amal-pmmeul`.
5. أخبر المستخدم أن ينفِّذ `git pull && bench migrate && bench restart`
   على السيرفر الفعلي، ولا تفترض نجاح الترحيل — انتظر تأكيده أو نتائج
   console الفعلية عند وجود شك.

---

## سجل مراحل التطوير الكبرى

- **Phase 1–2**: بناء السقالة الأساسية لعشرات DocTypes دورة حياة الأصل
  (قبل التوثيق الرسمي بهذا الملف).
- **Phase 3 — بوابة مدير الفرع**: صلاحيات مبنية على `User Permission`
  + `Custom DocPerm`، ودورة عمل أوامر العمل (رفض نهائي/إتمام بتكلفة
  قابلة للصفر)، وواجهة API متوافقة مع تطبيق موبايل مستقبلي
  (`api/branch_manager.py`). انظر `BRANCH_MANAGER_PORTAL_README.md`.
- **Phase 4 — مزايا صيانة احترافية**: Kanban/Calendar لأوامر العمل، QR
  code لكل أصل، تنبيهات حرجة فورية، مراقبة سلسلة تبريد، إعادة طلب قطع
  غيار تلقائي، بوابة مورِّد صيانة خارجي، Branch Health Score. انظر
  `PROFESSIONAL_MAINTENANCE_FEATURES_README.md`.
- **Phase 5 — صفحات الويزارد**: 4 صفحات Desk مستقلة (خطوة بخطوة) بدل
  نماذج طويلة، فوق نفس الـ API الموجود دون تكرار منطق. انظر
  `WIZARD_PAGES_README.md`.
- **Phase 6 — منصة EAM/CMMS مؤسسية (مكتملة، 16 بنداً عبر 4 أقسام)**:
  تعميق التكامل المالي (رسملة CWIP، صرف مخزني آلي لقطع الغيار، CapEx
  مقابل OpEx، شطب/تكهين، IFRS 16 Lease، TCO حقيقي)، محرك موثوقية متقدم
  (ISO 14224 PCR، صيانة مزدوجة المحفز، AHI/RUL، قطع غيار دوارة، غرامات
  SLA)، سلامة/امتثال (LOTO، قوائم فحص ديناميكية، ESG/كربون)، وطبقة
  Headless API (`api/v1/mobile.py`, `api/v1/telemetry.py`) لتطبيق
  Flutter وIoT مستقبلاً. كل بند مُدقَّق مقابل الكود الموجود فعلياً قبل
  أي تنفيذ (أغلب الحالات كانت "ابنِ فوق سقالة موجودة" أو "اربط بمنطق
  Core أصلي بدل تكراره"، وليس "أنشئ من الصفر"). التفاصيل الكاملة في
  `ENTERPRISE_EAM_PHASE6_README.md`.
