frappe.ui.form.on("Asset Disposal Execution", {
	refresh(frm) {
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("عرض فاتورة البيع"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			}, __("المحاسبة"));
		}
	}
});
