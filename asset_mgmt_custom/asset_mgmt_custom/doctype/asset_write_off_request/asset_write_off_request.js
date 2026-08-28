frappe.ui.form.on("Asset Write Off Request", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.journal_entry) {
            frm.add_custom_button(__("إنشاء قيد اليومية"), () => {
                frappe.confirm(
                    __("هل تريد إنشاء قيد محاسبي لشطب هذا الأصل؟ سيتم خصم القيمة الدفترية من حسابات الأصول."),
                    () => {
                        frappe.call({
                            method: "create_journal_entry",
                            doc: frm.doc,
                            freeze: true,
                            freeze_message: __("جارٍ إنشاء قيد اليومية..."),
                            callback(r) {
                                if (r.message) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("المحاسبة"));
        }

        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("عرض قيد اليومية"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("المحاسبة"));
        }
    }
});
