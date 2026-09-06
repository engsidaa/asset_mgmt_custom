frappe.pages['asset-coding-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('ترميز / تفعيل أصل'),
		single_column: true,
	});

	build_wizard(page);
};

function build_wizard(page) {
	const wiz_state = { before_file: null, after_file: null };

	new asset_mgmt_custom.Wizard({
		wrapper: page.body,
		title: __('ترميز / تفعيل أصل'),
		subtitle: __('الصق/انقش كود الأصل ووثِّقه بصورتين، ثم فعِّله تشغيلياً ليبدأ احتساب الإهلاك'),
		finish_label: __('تأكيد'),
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
						get_query: () => ({
							filters: {
								docstatus: 1,
								custom_operational_status: ['!=', 'Operational'],
							},
						}),
					}, 'asset');
					if (wizard.state.asset) control.set_value(wizard.state.asset);

					wizard._asset_info_box = $(`<div class="amc-wizard-summary-card" style="margin-top:12px; display:none;"></div>`).appendTo($body);

					control.df.onchange = async () => {
						const val = control.get_value();
						wizard.state.asset = val;
						wizard.state.asset_info = null;
						if (!val) {
							wizard._asset_info_box.hide();
							return;
						}
						const info = await frappe.db.get_value('Asset', val, [
							'asset_name', 'asset_category', 'custom_coding_status', 'custom_operational_status',
						]);
						const d = info.message || {};
						wizard.state.asset_info = d;
						wizard._asset_info_box.show().html(`
							<div class="row">
								<div class="col-sm-6"><span class="label">${__('الاسم')}</span><br><span class="value">${frappe.utils.escape_html(d.asset_name || '')}</span></div>
								<div class="col-sm-6"><span class="label">${__('الفئة')}</span><br><span class="value">${frappe.utils.escape_html(d.asset_category || '')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('حالة الترميز')}</span><br><span class="value">${frappe.utils.escape_html(d.custom_coding_status || '')}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('حالة التشغيل')}</span><br><span class="value">${frappe.utils.escape_html(d.custom_operational_status || '')}</span></div>
							</div>
						`);
					};
				},
				validate(wizard) {
					if (!wizard.state.asset) {
						wizard.show_error(__('يرجى اختيار الأصل.'));
						return false;
					}
					wizard.state.needs_coding = !wizard.state.asset_info || wizard.state.asset_info.custom_coding_status !== 'Coded';
					return true;
				},
			},
			{
				id: 'tagging',
				label: __('الترميز'),
				render($body, wizard) {
					if (!wizard.state.needs_coding) {
						$body.append(`<div class="alert alert-success">${__('هذا الأصل مُرمَّز بالفعل — يمكنك المتابعة مباشرة إلى التفعيل التشغيلي.')}</div>`);
						return;
					}

					$body.append(`<label class="control-label">${__('نوع الترميز')} *</label>`);
					const tag_type = wizard.make_field($body, {
						fieldtype: 'Select',
						fieldname: 'custom_tag_type',
						options: '\nBarcode\nRFID\nIron Code',
						reqd: 1,
					}, 'custom_tag_type');
					if (wizard.state.custom_tag_type) tag_type.set_value(wizard.state.custom_tag_type);

					const $sticker_wrap = $(`<div style="margin-top:15px; display:none;"></div>`).appendTo($body);
					$sticker_wrap.append(`<label class="control-label">${__('كود الملصق (Sticker Code)')} *</label>`);
					const sticker_code = wizard.make_field($sticker_wrap, { fieldtype: 'Data', fieldname: 'custom_sticker_code' }, 'custom_sticker_code');
					if (wizard.state.custom_sticker_code) sticker_code.set_value(wizard.state.custom_sticker_code);

					const $iron_wrap = $(`<div style="margin-top:15px; display:none;"></div>`).appendTo($body);
					$iron_wrap.append(`<label class="control-label">${__('كود الحديد (Iron Code)')} *</label>`);
					const iron_code = wizard.make_field($iron_wrap, { fieldtype: 'Data', fieldname: 'custom_iron_code' }, 'custom_iron_code');
					if (wizard.state.custom_iron_code) iron_code.set_value(wizard.state.custom_iron_code);

					function toggle_code_fields() {
						const t = tag_type.get_value();
						$sticker_wrap.toggle(t === 'Barcode' || t === 'RFID');
						$iron_wrap.toggle(t === 'Iron Code');
					}
					toggle_code_fields();
					tag_type.df.onchange = toggle_code_fields;

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('صورة قبل اللصق/النقش')} *</label>`);
					const $before_input = $(`<input type="file" accept="image/*" class="form-control">`).appendTo($body);
					const $before_preview = $(`<div style="margin-top:8px;"></div>`).appendTo($body);
					if (wiz_state.before_file) {
						$before_preview.html(`<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(wiz_state.before_file.name)}</span>`);
					}
					$before_input.on('change', (e) => {
						const file = e.target.files[0];
						wiz_state.before_file = file || null;
						$before_preview.html(file ? `<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(file.name)}</span>` : '');
					});

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('صورة بعد اللصق/النقش')} *</label>`);
					const $after_input = $(`<input type="file" accept="image/*" class="form-control">`).appendTo($body);
					const $after_preview = $(`<div style="margin-top:8px;"></div>`).appendTo($body);
					if (wiz_state.after_file) {
						$after_preview.html(`<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(wiz_state.after_file.name)}</span>`);
					}
					$after_input.on('change', (e) => {
						const file = e.target.files[0];
						wiz_state.after_file = file || null;
						$after_preview.html(file ? `<span class="text-muted">${__('تم اختيار صورة')}: ${frappe.utils.escape_html(file.name)}</span>` : '');
					});
				},
				validate(wizard) {
					if (!wizard.state.needs_coding) return true;

					wizard.state.custom_tag_type = wizard.controls.custom_tag_type.get_value();
					if (!wizard.state.custom_tag_type) {
						wizard.show_error(__('يرجى اختيار نوع الترميز.'));
						return false;
					}

					if (wizard.state.custom_tag_type === 'Iron Code') {
						wizard.state.custom_iron_code = wizard.controls.custom_iron_code.get_value();
						if (!wizard.state.custom_iron_code) {
							wizard.show_error(__('يرجى إدخال كود الحديد.'));
							return false;
						}
					} else {
						wizard.state.custom_sticker_code = wizard.controls.custom_sticker_code.get_value();
						if (!wizard.state.custom_sticker_code) {
							wizard.show_error(__('يرجى إدخال كود الملصق.'));
							return false;
						}
					}

					if (!wiz_state.before_file) {
						wizard.show_error(__('يرجى إرفاق صورة قبل اللصق/النقش.'));
						return false;
					}
					if (!wiz_state.after_file) {
						wizard.show_error(__('يرجى إرفاق صورة بعد اللصق/النقش.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'activation',
				label: __('التفعيل التشغيلي'),
				render($body, wizard) {
					if (wizard.state.activate_now === undefined) wizard.state.activate_now = true;

					$body.append(`
						<div class="amc-wizard-summary-card amc-action-choice" style="cursor:pointer; padding:20px;">
							<label style="cursor:pointer; margin:0;">
								<input type="checkbox" class="amc-activate-now-checkbox" ${wizard.state.activate_now ? 'checked' : ''}>
								${__('تفعيل الأصل تشغيلياً الآن (Set Operational) — سيبدأ احتساب الإهلاك من اليوم')}
							</label>
						</div>
						<p class="text-muted" style="margin-top:10px;">${__('إن لم تُفعِّله الآن، سيبقى الأصل بحالة "غير مكتمل" ويمكن تفعيله لاحقاً من نفس هذه الصفحة.')}</p>
					`);

					$body.find('.amc-activate-now-checkbox').on('change', function () {
						wizard.state.activate_now = $(this).is(':checked');
					});
				},
			},
			{
				id: 'review',
				label: __('التأكيد'),
				render($body, wizard) {
					const coding_html = wizard.state.needs_coding ? `
						<span class="label">${__('نوع الترميز')}</span><br>
						<span class="value">${frappe.utils.escape_html(wizard.state.custom_tag_type)}</span><br>
						<span class="label">${__('الكود')}</span><br>
						<span class="value">${frappe.utils.escape_html(wizard.state.custom_iron_code || wizard.state.custom_sticker_code || '')}</span>
					` : `<span class="value">${__('الأصل مُرمَّز بالفعل — لن يُعاد ترميزه.')}</span>`;

					$body.append(`
						<div class="amc-wizard-summary-card">
							<span class="label">${__('الأصل')}</span><br>
							<span class="value">${frappe.utils.escape_html(wizard.state.asset)}</span>
							<hr>
							${coding_html}
							<hr>
							<span class="label">${__('التفعيل التشغيلي')}</span><br>
							<span class="value">${wizard.state.activate_now ? __('سيُفعَّل الآن') : __('لن يُفعَّل الآن — لاحقاً')}</span>
						</div>
					`);
				},
			},
		],
		async finish(wizard) {
			if (wizard.state.needs_coding) {
				const values = { custom_tag_type: wizard.state.custom_tag_type };
				if (wizard.state.custom_tag_type === 'Iron Code') {
					values.custom_iron_code = wizard.state.custom_iron_code;
				} else {
					values.custom_sticker_code = wizard.state.custom_sticker_code;
				}
				await frappe.xcall('frappe.client.set_value', {
					doctype: 'Asset', name: wizard.state.asset, fieldname: values,
				});

				const before_res = await asset_mgmt_custom.Wizard.upload_file(wiz_state.before_file, {
					doctype: 'Asset', docname: wizard.state.asset, fieldname: 'custom_tagging_photo_before',
				});
				await frappe.xcall('frappe.client.set_value', {
					doctype: 'Asset', name: wizard.state.asset,
					fieldname: 'custom_tagging_photo_before', value: before_res.message.file_url,
				});

				const after_res = await asset_mgmt_custom.Wizard.upload_file(wiz_state.after_file, {
					doctype: 'Asset', docname: wizard.state.asset, fieldname: 'custom_tagging_photo',
				});
				await frappe.xcall('frappe.client.set_value', {
					doctype: 'Asset', name: wizard.state.asset,
					fieldname: 'custom_tagging_photo', value: after_res.message.file_url,
				});

				await frappe.xcall('asset_mgmt_custom.overrides.asset.mark_coded', {
					asset_name: wizard.state.asset,
				});
			}

			if (wizard.state.activate_now) {
				await frappe.xcall('asset_mgmt_custom.overrides.asset.set_operational', {
					asset_name: wizard.state.asset,
				});
			}

			frappe.show_alert({ message: __('تم تحديث الأصل بنجاح.'), indicator: 'green' });
			frappe.set_route('Form', 'Asset', wizard.state.asset);
		},
	});
}
