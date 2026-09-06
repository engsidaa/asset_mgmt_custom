frappe.ui.form.on('Asset Performance Rating', {
	refresh(frm) {
		if (frm.doc.asset) {
			frm.add_custom_button(__('احسب من مؤشر صحة الأصل (AHI)'), () => {
				frm.call('compute_from_health_data').then((r) => {
					if (!r.message) return;
					frm.refresh_fields();
					frappe.show_alert({
						message: __('تم الحساب — الدرجة الإجمالية: {0}', [r.message.overall_rating]),
						indicator: 'green',
					});
				});
			});
		}
	},
});
