frappe.ui.form.on('Asset Return Request', {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === 'Approved') {
			frm.add_custom_button(__('تعليم كمُعاد'), () => {
				frappe.confirm(
					__('سيُعلَّم الأصل كمُعاد فعلياً، وسيُغلَق تخصيص الموظف المرتبط (إن وُجد). متابعة؟'),
					() => {
						frm.call('mark_returned').then(() => {
							frappe.show_alert({ message: __('تم تعليم الأصل كمُعاد.'), indicator: 'green' });
							frm.reload_doc();
						});
					}
				);
			});
		}
	},
});
