frappe.ui.form.on("Asset Spare Part Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.stock_entry) {
			frm.add_custom_button(__("صرف القطعة (Stock Entry)"), () => {
				frappe.confirm(
					__("سيتم إنشاء حركة مخزون (Material Issue) لصرف الكمية المطلوبة من المستودع. متابعة؟"),
					() => {
						frappe.call({
							method: "issue_spare_part",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("جارٍ إنشاء حركة المخزون..."),
							callback(r) {
								if (r.message) {
									frm.reload_doc();
								}
							}
						});
					}
				);
			}, __("المخزون"));
		}

		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("عرض حركة المخزون"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			}, __("المخزون"));
		}
	}
});
