frappe.pages['asset-work-order-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('طلب صيانة جديد'),
		single_column: true,
	});

	build_wizard(page);
};

function build_wizard(page) {
	const wiz_state = { photo_file: null };

	new asset_mgmt_custom.Wizard({
		wrapper: page.body,
		title: __('طلب صيانة جديد'),
		subtitle: __('اختر الأصل، صف العطل، وأرسل الطلب مباشرة لفريق الصيانة'),
		finish_label: __('إرسال الطلب'),
		steps: [
			{
				id: 'asset',
				label: __('اختر الأصل'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('الأصل')} *</label>`);
					const control = wizard.make_field($body, {
						fieldtype: 'Link',
						fieldname: 'asset',
						options: 'Asset',
						reqd: 1,
						placeholder: __('ابحث عن الأصل بالاسم أو الكود...'),
					}, 'asset');

					if (wizard.state.asset) control.set_value(wizard.state.asset);

					wizard._asset_info_box = $(`<div class="amc-wizard-summary-card" style="margin-top:12px; display:none;"></div>`).appendTo($body);

					control.df.onchange = async () => {
						const val = control.get_value();
						wizard.state.asset = val;
						if (!val) {
							wizard._asset_info_box.hide();
							return;
						}
						const info = await frappe.db.get_value('Asset', val,
							['asset_name', 'asset_category', 'custom_branch', 'custom_operational_status']);
						const a = info.message || {};
						wizard._asset_info_box.show().html(`
							<div class="row">
								<div class="col-sm-6"><span class="label">${__('اسم الأصل')}</span><br><span class="value">${frappe.utils.escape_html(a.asset_name || '')}</span></div>
								<div class="col-sm-6"><span class="label">${__('الفئة')}</span><br><span class="value">${frappe.utils.escape_html(a.asset_category || '—')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الفرع')}</span><br><span class="value">${frappe.utils.escape_html(a.custom_branch || '—')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الحالة التشغيلية')}</span><br><span class="value">${frappe.utils.escape_html(a.custom_operational_status || '—')}</span></div>
							</div>
						`);
					};
				},
				validate(wizard) {
					if (!wizard.state.asset) {
						wizard.show_error(__('يرجى اختيار الأصل أولاً.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'problem',
				label: __('وصف العطل'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('صف العطل بالتفصيل')} *</label>`);
					const control = wizard.make_field($body, {
						fieldtype: 'Small Text',
						fieldname: 'problem_description',
						reqd: 1,
					}, 'problem_description');
					if (wizard.state.problem_description) control.set_value(wizard.state.problem_description);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('صورة العطل (اختياري)')}</label>`);
					const $file_row = $(`<div></div>`).appendTo($body);
					const $input = $(`<input type="file" accept="image/*" class="form-control">`).appendTo($file_row);
					const $preview = $(`<div style="margin-top:8px;"></div>`).appendTo($file_row);

					if (wiz_state.photo_file) {
						$preview.html(`<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(wiz_state.photo_file.name)}</span>`);
					}

					$input.on('change', (e) => {
						const file = e.target.files[0];
						wiz_state.photo_file = file || null;
						$preview.html(file ? `<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(file.name)}</span>` : '');
					});
				},
				validate(wizard) {
					const val = wizard.controls.problem_description.get_value();
					wizard.state.problem_description = val;
					if (!val || !val.trim()) {
						wizard.show_error(__('يرجى كتابة وصف للعطل.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'priority',
				label: __('الأولوية'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('نوع العمل')}</label>`);
					const work_type = wizard.make_field($body, {
						fieldtype: 'Select',
						fieldname: 'work_type',
						options: 'صيانة وقائية\nإصلاح\nفحص\nطارئ\nتحسين',
					}, 'work_type');
					work_type.set_value(wizard.state.work_type || 'إصلاح');

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('الأولوية')}</label>`);
					const priority = wizard.make_field($body, {
						fieldtype: 'Select',
						fieldname: 'priority',
						options: 'عادي\nمتوسط\nعاجل\nحرج',
					}, 'priority');
					priority.set_value(wizard.state.priority || 'عادي');
				},
				validate(wizard) {
					wizard.state.work_type = wizard.controls.work_type.get_value();
					wizard.state.priority = wizard.controls.priority.get_value();
					return true;
				},
			},
			{
				id: 'review',
				label: __('المراجعة والإرسال'),
				render($body, wizard) {
					$body.append(`
						<div class="amc-wizard-summary-card">
							<div class="row">
								<div class="col-sm-6"><span class="label">${__('الأصل')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.asset)}</span></div>
								<div class="col-sm-6"><span class="label">${__('نوع العمل')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.work_type)}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الأولوية')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.priority)}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('صورة مرفقة')}</span><br><span class="value">${wiz_state.photo_file ? __('نعم') : __('لا')}</span></div>
							</div>
							<hr>
							<span class="label">${__('وصف العطل')}</span><br>
							<span class="value">${frappe.utils.escape_html(wizard.state.problem_description)}</span>
						</div>
					`);
				},
			},
		],
		async finish(wizard) {
			const r = await frappe.xcall(
				'asset_mgmt_custom.api.branch_manager.create_maintenance_request',
				{
					asset: wizard.state.asset,
					problem_description: wizard.state.problem_description,
					work_type: wizard.state.work_type,
					priority: wizard.state.priority,
				}
			);

			if (wiz_state.photo_file && r && r.name) {
				await asset_mgmt_custom.Wizard.upload_file(wiz_state.photo_file, {
					doctype: 'Asset Work Order',
					docname: r.name,
					fieldname: 'fault_photo',
				});
			}

			frappe.show_alert({ message: __('تم إرسال طلب الصيانة بنجاح: {0}', [r.name]), indicator: 'green' });
			frappe.set_route('Form', 'Asset Work Order', r.name);
		},
	});
}
