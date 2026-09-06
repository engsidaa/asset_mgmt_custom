frappe.ui.form.on('Asset Vendor Performance Rating', {
	refresh(frm) {
		if (frm.doc.supplier) {
			frm.add_custom_button(__('احسب من بيانات أوامر العمل الفعلية'), () => {
				frm.call('compute_from_work_orders').then((r) => {
					if (!r.message) return;
					frm.refresh_fields();
					frappe.show_alert({
						message: __('تم الحساب من {0} أمر عمل — راجع الدرجات وأكمل باقي المعايير يدوياً.', [r.message.work_order_count]),
						indicator: 'green',
					});
				});
			});
		}
	},
});
