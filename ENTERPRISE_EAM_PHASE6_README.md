# Phase 6 — منصة EAM/CMMS مؤسسية: التوثيق الكامل

توثيق تراكمي لمرحلة تطوير "asset_mgmt_custom" إلى منصة إدارة أصول
ومرافق وصيانة على مستوى مؤسسي، وفق الترتيب المعتمد: **التكامل المالي
أولاً**، ثم محرك الموثوقية، ثم السلامة/الامتثال، ثم طبقة الـ API
الخارجية. يُحدَّث هذا الملف مع كل بند يُنجَز — راجع أيضاً `CLAUDE.md`
للمحددات المعمارية الصارمة الحاكمة لكل ما يلي.

**تنويه هام:** قبل أي تنفيذ، جرى مسح كامل لِـ DocTypes الموجودة فعلياً
في هذا التطبيق (`asset_mgmt_custom/asset_mgmt_custom/doctype/`) — تبيَّن
أن **معظم** الأسماء الواردة في مواصفة "EAM المؤسسية" (asset_capex_budget،
asset_lease، asset_warranty_claim، asset_maintenance_sla_policy،
asset_vendor_contract، asset_write_off_request، asset_disposal_execution،
asset_energy_log، asset_fuel_log، asset_safety_inspection،
asset_work_permit، ...) **موجودة بالفعل كسقالة**، لكن أغلبها بمنطق أعمال
شبه معدوم (بعضها ملف `.py` سطر واحد فقط `pass`). التنفيذ هنا يبني **فوق**
هذه السقالة، ولا يُنشئ بنية موازية أو مكررة لها.

---

## القسم أ: التكامل المالي والمحاسبي العميق

### 1) رسملة الـ CWIP إلى أصل ثابت (CWIP → Fixed Asset)

**اكتشاف مهم قبل أي كود:** رسملة الـ CWIP بالكامل — الترحيل التلقائي
من حساب "أصول تحت التنفيذ" إلى حساب "الأصول الثابتة" عند تسليم الأصل —
**مبنية بالفعل في ERPNext الأساسي** ولا تحتاج أي كود مخصص:
- `Asset Category.enable_cwip_accounting` (حقل Core جاهز).
- `Asset Category Account.capital_work_in_progress_account` +
  `fixed_asset_account` (حقول Core جاهزة، تُضبط لكل شركة/فئة).
- `Asset.make_gl_entries()` (كود Core في
  `erpnext/assets/doctype/asset/asset.py`) يُستدعى تلقائياً عند تسليم
  (submit) الأصل، ويُنشئ قيد التحويل (دائن CWIP / مدين الأصل الثابت)
  بالقيمة الكاملة، مستخدماً `self.cost_center` مباشرة.
- عند شراء صنف مُعلَّم `is_fixed_asset=1` عبر Purchase Receipt/Purchase
  Invoice، ينشئ ERPNext تلقائياً سجل **Asset** كمسودة
  (`buying_controller.make_asset()`) — لا حاجة لمستند "شهادة استلام"
  منفصل، فالـ Purchase Receipt نفسه هو لحظة الاستلام.

**بناء كود مخصص لتكرار هذا كان سيُصادم مباشرة مع منطق Core (قيود مزدوجة
محتملة)** — لذا الفجوة الحقيقية الوحيدة التي عُولجت هنا:

- **الفجوة**: `make_asset()` الأساسي يضبط `location` فقط على الأصل
  الجديد، ولا يعرف شيئاً عن `custom_branch`/`cost_center` الخاصين بهذا
  التطبيق — فكان قيد الرسملة التلقائي (الذي يستخدم `self.cost_center`
  كما ذُكر) يُرحَّل بمركز تكلفة فارغ لأي أصل يُشترى عبر هذه الآلية.
  **الإصلاح**: `overrides/asset.py` → `_inherit_branch_and_cost_center()`
  (تُستدعى من `validate()`) تفرض هرمية `Company -> Branch -> Location ->
  Asset`: تشتق `custom_branch` من `Branch.custom_default_location`
  (مطابقة عكسية بموقع الأصل)، وتشتق `cost_center` من
  `Location.custom_cost_center` أو مركز تكلفة الفرع، تلقائياً، دون إدخال
  يدوي.
- **سلسلة التتبع الكاملة** (Asset Requisition → Material Request →
  Purchase Receipt → Asset) كانت **مقطوعة فعلياً وبصمت**: الحقل
  `Material Request.custom_source_asset_requisition` الذي كان الكود
  القديم في `asset_requisition.py::create_purchase_requisition()`
  يحاول ضبطه، **لم يكن موجوداً إطلاقاً** كحقل مخصص — الشرط الدفاعي
  `if frappe.db.exists("Custom Field", ...)` كان يُرجِع `False` دائماً،
  فالحقل يُترك `None` دائماً. تم:
  1. إضافة `Material Request.custom_source_asset_requisition` (Link)
     فعلياً في `fixtures/custom_field.json`.
  2. تبسيط `create_purchase_requisition()` لضبطه مباشرة.
  3. إضافة `Asset.custom_source_requisition` و
     `Asset Requisition.linked_asset` (رابطان في الاتجاهين)، وربطهما
     تلقائياً في `overrides/asset.py::_link_source_requisition()`
     (تُستدعى من `after_insert()`) بتتبُّع
     `Purchase Receipt Item.material_request` للخلف.

**الإعداد المطلوب منك** (بيانات فقط، لا كود): فعِّل
`Enable Capital Work in Progress Accounting` على فئات الأصول الرأسمالية
(معدات كبيرة، مطابخ، تبريد...)، واضبط `Capital Work in Progress Account`
و`Fixed Asset Account` على `Asset Category Account` لكل شركة.

**اختبار:** أنشئ Purchase Receipt لصنف `is_fixed_asset=1` مرتبط بـ
Material Request صادر من Asset Requisition ← تأكد أن الأصل المُنشأ
تلقائياً يحمل `custom_branch`/`cost_center` صحيحين فوراً، وأن
`custom_source_requisition` يشير لطلب الأصل الأصلي وأن
`Asset Requisition.linked_asset` يشير للأصل ← فعِّل CWIP على الفئة وحدِّد
الحسابات ← سلِّم (submit) الأصل ← تأكد من ظهور قيد يومية تلقائي حقيقي
(Core) بمركز التكلفة الصحيح.

---

*(الأقسام التالية — الصرف المخزني الآلي، CapEx/OpEx، الشطب، الإيجار
IFRS16، TCO، ثم محرك الموثوقية والسلامة والـ API — تُضاف هنا تباعاً مع
كل بند يُنجَز.)*
