frappe.ui.form.on("Asset Work Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status !== "مكتمل" && frm.doc.status !== "ملغي") {
			frm.add_custom_button(__("إتمام أمر العمل"), () => {
				frappe.confirm(
					__("سيتم تحديد الحالة كـ 'مكتمل' وترحيل تكلفته الفعلية محاسبياً (إن وُجدت). متابعة؟"),
					() => {
						frappe.call({
							method: "frappe.client.set_value",
							args: {
								doctype: frm.doc.doctype,
								name: frm.doc.name,
								fieldname: "status",
								value: "مكتمل",
							},
							freeze: true,
							freeze_message: __("جارٍ إتمام أمر العمل..."),
							callback() {
								frm.reload_doc();
							},
						});
					}
				);
			}, __("الحالة"));
		}

		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("عرض قيد اليومية"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
			}, __("المحاسبة"));
		}
	},
});
