frappe.ui.form.on('Asset Complaint', {
	refresh(frm) {
		if (!frm.doc.escalated_work_order && !['Resolved', 'Closed'].includes(frm.doc.status)) {
			frm.add_custom_button(__('تصعيد لأمر عمل'), () => {
				frappe.confirm(
					__('سيُنشأ أمر عمل صيانة رسمي من هذه الشكوى. متابعة؟'),
					() => {
						frm.call('escalate_to_work_order').then((r) => {
							if (!r.message) return;
							frappe.show_alert({ message: __('تم إنشاء أمر العمل {0}', [r.message]), indicator: 'green' });
							frm.reload_doc();
						});
					}
				);
			});
		}
	},
});
