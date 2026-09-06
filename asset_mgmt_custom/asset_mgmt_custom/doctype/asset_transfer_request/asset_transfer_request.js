frappe.ui.form.on('Asset Transfer Request', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.status === 'Pending') {
			frm.add_custom_button(__('اعتماد'), () => {
				frm.call('approve').then(() => frm.reload_doc());
			}, __('الموافقة'));

			frm.add_custom_button(__('رفض'), () => {
				frappe.prompt(
					{ fieldtype: 'Small Text', fieldname: 'reason', label: __('سبب الرفض'), reqd: 1 },
					(values) => {
						frm.call('reject', { reason: values.reason }).then(() => frm.reload_doc());
					},
					__('رفض طلب النقل')
				);
			}, __('الموافقة'));
		}

		if (frm.doc.status === 'Approved' && !frm.doc.asset_movement) {
			frm.add_custom_button(__('تنفيذ النقل الفعلي'), () => {
				frappe.confirm(
					__('سيُنشأ حركة نقل فعلية (Asset Movement) وتُنقَل ملكية الأصل للفرع الجديد. متابعة؟'),
					() => {
						frm.call('execute_transfer').then((r) => {
							if (!r.message) return;
							frappe.show_alert({ message: __('تم تنفيذ النقل عبر {0}', [r.message]), indicator: 'green' });
							frm.reload_doc();
						});
					}
				);
			});
		}
	},
});
