frappe.pages['work-order-completion-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('إتمام / رفض أمر عمل'),
		single_column: true,
	});

	build_wizard(page);
};

function build_wizard(page) {
	const wiz_state = { photo_file: null };

	new asset_mgmt_custom.Wizard({
		wrapper: page.body,
		title: __('إتمام / رفض أمر عمل'),
		subtitle: __('اختر أمر العمل، حدِّد ما إذا كان مكتملاً أو مرفوضاً، وأدخِل التفاصيل'),
		finish_label: __('تأكيد'),
		steps: [
			{
				id: 'work_order',
				label: __('اختر أمر العمل'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('أمر العمل')} *</label>`);
					const control = wizard.make_field($body, {
						fieldtype: 'Link',
						fieldname: 'work_order',
						options: 'Asset Work Order',
						reqd: 1,
						get_query: () => ({
							filters: {
								docstatus: 1,
								status: ['in', ['مفتوح', 'قيد التنفيذ', 'معلق']],
							},
						}),
					}, 'work_order');
					if (wizard.state.work_order) control.set_value(wizard.state.work_order);

					wizard._wo_info_box = $(`<div class="amc-wizard-summary-card" style="margin-top:12px; display:none;"></div>`).appendTo($body);

					control.df.onchange = async () => {
						const val = control.get_value();
						wizard.state.work_order = val;
						if (!val) {
							wizard._wo_info_box.hide();
							return;
						}
						const info = await frappe.db.get_value('Asset Work Order', val,
							['title', 'asset_name', 'priority', 'status', 'problem_description']);
						const d = info.message || {};
						wizard._wo_info_box.show().html(`
							<div class="row">
								<div class="col-sm-6"><span class="label">${__('العنوان')}</span><br><span class="value">${frappe.utils.escape_html(d.title || '')}</span></div>
								<div class="col-sm-6"><span class="label">${__('الأصل')}</span><br><span class="value">${frappe.utils.escape_html(d.asset_name || '')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الأولوية')}</span><br><span class="value">${frappe.utils.escape_html(d.priority || '')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الحالة')}</span><br><span class="value">${frappe.utils.escape_html(d.status || '')}</span></div>
							</div>
							<hr>
							<span class="label">${__('وصف المشكلة')}</span><br>
							<span class="value">${frappe.utils.escape_html(d.problem_description || '—')}</span>
						`);
					};
				},
				validate(wizard) {
					if (!wizard.state.work_order) {
						wizard.show_error(__('يرجى اختيار أمر العمل.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'action',
				label: __('الإجراء'),
				render($body, wizard) {
					$body.append(`<p>${__('ماذا تريد أن تفعل بهذا الأمر؟')}</p>`);
					const $row = $(`<div class="row"></div>`).appendTo($body);
					const $complete = $(`
						<div class="col-sm-6">
							<div class="amc-wizard-summary-card amc-action-choice" data-action="complete" style="cursor:pointer; text-align:center; padding:25px;">
								<div style="font-size:28px;">✅</div>
								<b>${__('إتمام الأمر')}</b>
							</div>
						</div>
					`).appendTo($row);
					const $reject = $(`
						<div class="col-sm-6">
							<div class="amc-wizard-summary-card amc-action-choice" data-action="reject" style="cursor:pointer; text-align:center; padding:25px;">
								<div style="font-size:28px;">⛔</div>
								<b>${__('رفض الأمر')}</b>
							</div>
						</div>
					`).appendTo($row);

					function highlight() {
						$row.find('.amc-action-choice').css('border-color', 'var(--border-color, #d1d8dd)');
						$row.find(`.amc-action-choice[data-action="${wizard.state.action}"]`).css('border-color', 'var(--primary, #2563eb)');
					}
					if (wizard.state.action) highlight();

					$row.find('.amc-action-choice').on('click', function () {
						wizard.state.action = $(this).data('action');
						highlight();
					});
				},
				validate(wizard) {
					if (!wizard.state.action) {
						wizard.show_error(__('يرجى اختيار إتمام أو رفض.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'details',
				label: __('التفاصيل'),
				render($body, wizard) {
					if (wizard.state.action === 'complete') {
						$body.append(`<label class="control-label">${__('التكلفة الفعلية')}</label>`);
						const actual_cost = wizard.make_field($body, { fieldtype: 'Currency', fieldname: 'actual_cost' }, 'actual_cost');
						actual_cost.set_value(wizard.state.actual_cost || 0);

						$body.append(`<label class="control-label" style="margin-top:15px;">${__('ملاحظات الإتمام')}</label>`);
						const notes = wizard.make_field($body, { fieldtype: 'Small Text', fieldname: 'completion_notes' }, 'completion_notes');
						if (wizard.state.completion_notes) notes.set_value(wizard.state.completion_notes);

						$body.append(`<label class="control-label" style="margin-top:15px;">${__('صورة الإتمام (اختياري)')}</label>`);
						const $input = $(`<input type="file" accept="image/*" class="form-control">`).appendTo($body);
						const $preview = $(`<div style="margin-top:8px;"></div>`).appendTo($body);
						if (wiz_state.photo_file) {
							$preview.html(`<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(wiz_state.photo_file.name)}</span>`);
						}
						$input.on('change', (e) => {
							const file = e.target.files[0];
							wiz_state.photo_file = file || null;
							$preview.html(file ? `<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(file.name)}</span>` : '');
						});
					} else {
						$body.append(`<label class="control-label">${__('سبب الرفض')} *</label>`);
						const reason = wizard.make_field($body, { fieldtype: 'Small Text', fieldname: 'rejection_reason', reqd: 1 }, 'rejection_reason');
						if (wizard.state.rejection_reason) reason.set_value(wizard.state.rejection_reason);
					}
				},
				validate(wizard) {
					if (wizard.state.action === 'complete') {
						wizard.state.actual_cost = wizard.controls.actual_cost.get_value();
						wizard.state.completion_notes = wizard.controls.completion_notes.get_value();
					} else {
						wizard.state.rejection_reason = wizard.controls.rejection_reason.get_value();
						if (!wizard.state.rejection_reason || !wizard.state.rejection_reason.trim()) {
							wizard.show_error(__('يرجى كتابة سبب الرفض.'));
							return false;
						}
					}
					return true;
				},
			},
			{
				id: 'review',
				label: __('التأكيد'),
				render($body, wizard) {
					if (wizard.state.action === 'complete') {
						$body.append(`
							<div class="amc-wizard-summary-card">
								<span class="label">${__('التكلفة الفعلية')}</span><br>
								<span class="value">${wizard.state.actual_cost || 0}</span>
								<hr>
								<span class="label">${__('ملاحظات الإتمام')}</span><br>
								<span class="value">${frappe.utils.escape_html(wizard.state.completion_notes || '—')}</span>
							</div>
							<p class="text-muted">${__('سيتم تحديد الحالة كـ "مكتمل" وترحيل تكلفته الفعلية محاسبياً (إن وُجدت).')}</p>
						`);
					} else {
						$body.append(`
							<div class="amc-wizard-summary-card">
								<span class="label">${__('سبب الرفض')}</span><br>
								<span class="value">${frappe.utils.escape_html(wizard.state.rejection_reason)}</span>
							</div>
							<p class="text-muted">${__('هذا الرفض نهائي ولا يمكن التراجع عنه.')}</p>
						`);
					}
				},
			},
		],
		async finish(wizard) {
			if (wizard.state.action === 'complete') {
				if (wizard.state.actual_cost) {
					await frappe.xcall('frappe.client.set_value', {
						doctype: 'Asset Work Order',
						name: wizard.state.work_order,
						fieldname: 'actual_cost',
						value: wizard.state.actual_cost,
					});
				}
				if (wizard.state.completion_notes) {
					await frappe.xcall('frappe.client.set_value', {
						doctype: 'Asset Work Order',
						name: wizard.state.work_order,
						fieldname: 'completion_notes',
						value: wizard.state.completion_notes,
					});
				}
				if (wiz_state.photo_file) {
					await asset_mgmt_custom.Wizard.upload_file(wiz_state.photo_file, {
						doctype: 'Asset Work Order',
						docname: wizard.state.work_order,
					});
				}
				await frappe.xcall('run_doc_method', {
					dt: 'Asset Work Order',
					dn: wizard.state.work_order,
					method: 'complete_work_order',
				});
				frappe.show_alert({ message: __('تم إتمام أمر العمل بنجاح.'), indicator: 'green' });
			} else {
				await frappe.xcall('run_doc_method', {
					dt: 'Asset Work Order',
					dn: wizard.state.work_order,
					method: 'reject_work_order',
					args: { reason: wizard.state.rejection_reason },
				});
				frappe.show_alert({ message: __('تم رفض أمر العمل.'), indicator: 'orange' });
			}

			frappe.set_route('Form', 'Asset Work Order', wizard.state.work_order);
		},
	});
}
