import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt


class AssetWriteoffRequest(Document):
    def on_submit(self):
        self.db_set("status", "Pending Approval")

    def on_cancel(self):
        self.db_set("status", "Draft")

    @frappe.whitelist()
    def create_journal_entry(self):
        """Create a Journal Entry for the write-off loss after approval."""
        if self.status not in ("Approved",):
            frappe.throw(_("يجب أن يكون الطلب بحالة 'موافق' قبل إنشاء القيد المحاسبي."))

        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            frappe.throw(_(f"القيد المحاسبي {self.journal_entry} موجود بالفعل."))

        asset = frappe.get_doc("Asset", self.asset)
        company = asset.company or frappe.defaults.get_user_default("Company")

        if asset.status in ("Scrapped", "Sold"):
            frappe.throw(_(
                "Asset {0} is already disposed of (status: {1}). Cannot post a duplicate "
                "write-off journal entry for it."
            ).format(asset.name, asset.status))

        # estimated_loss_value هو الحقل الحقيقي في هذا المستند (اللي المستخدم
        # بيملاه فعلياً من الشاشة) — نسخة سابقة من هذا الكود كانت بتقرأ
        # book_value/amount بدل منه، وهما حقلان غير موجودين إطلاقاً في هذا
        # الـ DocType، فكانت القيمة المُدخَلة من المستخدم بتتجاهَل بالكامل
        # وبيُحتسَب مبلغ تلقائي من جدول الإهلاك دايماً بدلها.
        book_value = flt(self.get("estimated_loss_value"))

        if not book_value:
            # لا توجد قيمة خسارة مُقدَّرة مُدخَلة يدوياً — نحسبها من قيمة
            # الأصل بعد الإهلاك عبر Asset.get_value_after_depreciation()،
            # نفس الدالة الأساسية (Core) التي يعتمد عليها Asset Value
            # Adjustment وdepreciation.py لنفس الغرض — بدل استعلام SQL يدوي
            # كان يُعيد 0 دائماً لأي أصل (كان يستعلم WHERE parent=<اسم
            # الأصل> مباشرة على جدول Depreciation Schedule الفرعي، رغم أن
            # حقل parent فيه يشاور على "Asset Depreciation Schedule" الأب،
            # وليس على الأصل نفسه أبداً — فالقيمة الدفترية كانت دائماً =
            # سعر الشراء الكامل بدون خصم أي إهلاك متراكم فعلي).
            book_value = asset.get_value_after_depreciation()

        if not book_value:
            frappe.throw(_("لا يمكن تحديد القيمة الدفترية للأصل. يرجى تحديد المبلغ يدوياً."))

        gross_amount = flt(asset.gross_purchase_amount)
        # مجمع الإهلاك = سعر الشراء الكامل - القيمة الدفترية الحالية. لازم
        # يُقفَل صراحة في هذا القيد أيضاً، وإلا يبقى حساب "الأصول الثابتة"
        # (المُسجَّل بالسعر الإجمالي دائماً) يحمل رصيداً متبقياً = مجمع
        # الإهلاك إلى الأبد لهذا الأصل تحديداً، حتى بعد شطبه بالكامل من
        # السجلات — القيد القديم كان يُقيِّد فقط القيمة الدفترية على
        # الطرفين (مدين الشطب / دائن الأصول الثابتة)، فلا يُقفل مجمع
        # الإهلاك ولا يُقفل حساب الأصول الثابتة على قيمته الإجمالية الفعلية.
        accumulated_depreciation = max(gross_amount - flt(book_value), 0)

        category_account = frappe.db.get_value(
            "Asset Category Account",
            {"parent": asset.asset_category, "company_name": company},
            ["fixed_asset_account", "accumulated_depreciation_account"],
            as_dict=True,
        )
        asset_account = category_account and category_account.fixed_asset_account
        accumulated_depreciation_account = category_account and category_account.accumulated_depreciation_account

        if not asset_account:
            frappe.throw(_(
                "لا يوجد حساب أصول ثابتة مرتبط بفئة الأصل. "
                "تأكد من إعداد Asset Category Accounts للشركة."
            ))
        if accumulated_depreciation > 0 and not accumulated_depreciation_account:
            frappe.throw(_(
                "لا يوجد حساب مجمع إهلاك مرتبط بفئة الأصل. "
                "تأكد من إعداد Asset Category Accounts للشركة."
            ))

        # Write-off expense account
        # disposal_account ("Gain/Loss Account on Asset Disposal") هو الحقل
        # الحقيقي والمخصص لهذا الغرض تحديداً في Company. النسخة السابقة
        # كانت بتستخدم write_off_account كأولوية أولى، وبتحاول كـ fallback
        # قراءة حقل "loss_on_disposal_of_assets" غير موجود إطلاقاً في
        # ERPNext — كان هيتسبب في خطأ SQL خام ("Unknown column") لو
        # write_off_account فاضي، بدل رسالة واضحة.
        writeoff_account = (
            frappe.db.get_value("Company", company, "disposal_account")
            or frappe.db.get_value("Company", company, "write_off_account")
        )
        if not writeoff_account:
            frappe.throw(_(
                "لا يوجد حساب شطب مُعيَّن في إعدادات الشركة. "
                "حدد 'Write Off Account' في إعدادات الشركة."
            ))

        # مركز التكلفة إلزامي في ERPNext لأي حساب أرباح وخسائر (زي حساب
        # الشطب هنا) — لو الحقل فاضي على المستند، نرجع لمركز تكلفة الأصل
        # نفسه بدل ما نسيب القيد يفشل بدون مركز تكلفة.
        cost_center = self.cost_center or asset.get("cost_center")

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Write Off Entry"
        je.posting_date = self.write_off_date or today()
        je.company = company
        je.user_remark = f"شطب الأصل: {asset.asset_name} — {self.name}"
        if cost_center:
            je.cost_center = cost_center

        # ملاحظة: reference_type لازم يكون واحداً من القيم المسموحة في
        # Journal Entry Account (Sales/Purchase Invoice، Asset، إلخ) —
        # "Asset Write Off Request" (self.doctype) مش من ضمنها، وكانت
        # بتُفشل هذا القيد دايماً. نرجع للأصل نفسه كمرجع بدلاً منه.
        asset_reference = {"reference_type": "Asset", "reference_name": self.asset}

        if accumulated_depreciation > 0:
            # Debit: يُقفل مجمع الإهلاك المتراكم على هذا الأصل بالكامل
            je.append("accounts", {
                "account": accumulated_depreciation_account,
                "debit_in_account_currency": accumulated_depreciation,
                "cost_center": cost_center,
                **asset_reference,
            })

        # Debit: خسارة الشطب (القيمة الدفترية المتبقية فقط)
        je.append("accounts", {
            "account": writeoff_account,
            "debit_in_account_currency": book_value,
            "cost_center": cost_center,
            **asset_reference,
        })

        # Credit: يُقفل حساب الأصول الثابتة على قيمته الإجمالية الكاملة
        # (سعر الشراء)، وليس القيمة الدفترية فقط — وإلا يبقى فرق = مجمع
        # الإهلاك عالقاً في الحساب إلى الأبد لهذا الأصل تحديداً.
        je.append("accounts", {
            "account": asset_account,
            "credit_in_account_currency": gross_amount,
            "cost_center": cost_center,
            **asset_reference,
        })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("journal_entry", je.name)
        self.db_set("status", "Executed")

        frappe.db.set_value(
            "Asset", asset.name,
            {"status": "Scrapped", "disposal_date": self.write_off_date or today()},
            update_modified=False,
        )

        frappe.msgprint(
            f"تم إنشاء قيد اليومية: <a href='/app/journal-entry/{je.name}'>{je.name}</a>",
            alert=True, indicator="green"
        )
        return je.name
