frappe.pages['branch-onboarding-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('معالج فتح فرع جديد'),
		single_column: true,
	});

	build_wizard(page);
};

function build_wizard(page) {
	new asset_mgmt_custom.Wizard({
		wrapper: page.body,
		title: __('معالج فتح فرع جديد'),
		subtitle: __('ينشئ مركز التكلفة والمخزن والموقع الافتراضي للفرع دفعة واحدة، بدل إعداد كل عنصر بمعزل عن الآخر'),
		finish_label: __('إنشاء الفرع'),
		steps: [
			{
				id: 'basic',
				label: __('بيانات الفرع الأساسية'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('اسم الفرع')} *</label>`);
					const branch_name = wizard.make_field($body, {
						fieldtype: 'Data', fieldname: 'branch_name', reqd: 1,
					}, 'branch_name');
					if (wizard.state.branch_name) branch_name.set_value(wizard.state.branch_name);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('الشركة')} *</label>`);
					const company = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'company', options: 'Company', reqd: 1,
						default: frappe.defaults.get_default('company'),
					}, 'company');
					company.set_value(wizard.state.company || frappe.defaults.get_default('company') || '');

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('المنطقة الجغرافية (اختياري)')}</label>`);
					const territory = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'territory', options: 'Territory',
					}, 'territory');
					if (wizard.state.territory) territory.set_value(wizard.state.territory);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('مدير الفرع (اختياري)')}</label>`);
					const branch_manager = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'branch_manager', options: 'User',
					}, 'branch_manager');
					if (wizard.state.branch_manager) branch_manager.set_value(wizard.state.branch_manager);
				},
				validate(wizard) {
					wizard.state.branch_name = wizard.controls.branch_name.get_value();
					wizard.state.company = wizard.controls.company.get_value();
					wizard.state.territory = wizard.controls.territory.get_value();
					wizard.state.branch_manager = wizard.controls.branch_manager.get_value();

					if (!wizard.state.branch_name) {
						wizard.show_error(__('يرجى إدخال اسم الفرع.'));
						return false;
					}
					if (!wizard.state.company) {
						wizard.show_error(__('يرجى اختيار الشركة.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'hierarchy',
				label: __('مركز التكلفة والمخزن والموقع'),
				render($body, wizard) {
					$body.append(`<p class="text-muted">${__('اترك المربع مؤشَّراً لإنشاء عنصر جديد باسم الفرع تلقائياً، أو أزل الإشارة واختر عنصراً موجوداً بالفعل.')}</p>`);

					const make_pair = (key, check_label, link_label, options) => {
						$body.append(`<div style="margin-top:18px; border-top:1px solid var(--border-color,#eee); padding-top:12px;">`);
						const check = wizard.make_field($body, {
							fieldtype: 'Check', fieldname: `create_${key}`, label: check_label, default: 1,
						}, `create_${key}`);
						check.set_value(wizard.state[`create_${key}`] === 0 ? 0 : 1);

						$body.append(`<label class="control-label" style="margin-top:8px;">${link_label}</label>`);
						const link = wizard.make_field($body, {
							fieldtype: 'Link', fieldname: key, options,
						}, key);
						if (wizard.state[key]) link.set_value(wizard.state[key]);
						$body.append(`</div>`);
					};

					make_pair('cost_center', __('إنشاء مركز تكلفة جديد'), __('أو اختر مركز تكلفة موجود'), 'Cost Center');
					make_pair('warehouse', __('إنشاء مخزن جديد'), __('أو اختر مخزناً موجوداً'), 'Warehouse');
					make_pair('location', __('إنشاء موقع جديد'), __('أو اختر موقعاً موجوداً'), 'Location');
				},
				validate(wizard) {
					wizard.state.create_cost_center = wizard.controls.create_cost_center.get_value() ? 1 : 0;
					wizard.state.cost_center = wizard.controls.cost_center.get_value();
					wizard.state.create_warehouse = wizard.controls.create_warehouse.get_value() ? 1 : 0;
					wizard.state.warehouse = wizard.controls.warehouse.get_value();
					wizard.state.create_location = wizard.controls.create_location.get_value() ? 1 : 0;
					wizard.state.location = wizard.controls.location.get_value();

					if (!wizard.state.create_cost_center && !wizard.state.cost_center) {
						wizard.show_error(__('اختر مركز تكلفة موجود، أو أشِّر على "إنشاء مركز تكلفة جديد".'));
						return false;
					}
					if (!wizard.state.create_warehouse && !wizard.state.warehouse) {
						wizard.show_error(__('اختر مخزناً موجوداً، أو أشِّر على "إنشاء مخزن جديد".'));
						return false;
					}
					if (!wizard.state.create_location && !wizard.state.location) {
						wizard.show_error(__('اختر موقعاً موجوداً، أو أشِّر على "إنشاء موقع جديد".'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'review',
				label: __('المراجعة'),
				render($body, wizard) {
					const line = (label, value) => `
						<div class="col-sm-6" style="margin-top:8px;">
							<span class="label">${label}</span><br>
							<span class="value">${frappe.utils.escape_html(value || '—')}</span>
						</div>
					`;
					$body.append(`
						<div class="amc-wizard-summary-card">
							<div class="row">
								${line(__('اسم الفرع'), wizard.state.branch_name)}
								${line(__('الشركة'), wizard.state.company)}
								${line(__('مركز التكلفة'), wizard.state.create_cost_center ? __('جديد: {0}', [wizard.state.branch_name]) : wizard.state.cost_center)}
								${line(__('المخزن'), wizard.state.create_warehouse ? __('جديد: {0}', [wizard.state.branch_name]) : wizard.state.warehouse)}
								${line(__('الموقع'), wizard.state.create_location ? __('جديد: {0}', [wizard.state.branch_name]) : wizard.state.location)}
								${line(__('مدير الفرع'), wizard.state.branch_manager)}
							</div>
						</div>
						<p class="text-muted" style="margin-top:12px;">${__('سيُنشأ الفرع مرتبطاً بكل ما سبق دفعة واحدة عند الضغط على "إنشاء الفرع".')}</p>
					`);
				},
			},
		],
		async finish(wizard) {
			const created = await frappe.xcall('asset_mgmt_custom.setup.branch_onboarding.onboard_new_branch', {
				branch_name: wizard.state.branch_name,
				company: wizard.state.company,
				territory: wizard.state.territory,
				branch_manager: wizard.state.branch_manager,
				create_cost_center: wizard.state.create_cost_center,
				cost_center: wizard.state.cost_center,
				create_warehouse: wizard.state.create_warehouse,
				warehouse: wizard.state.warehouse,
				create_location: wizard.state.create_location,
				location: wizard.state.location,
			});

			frappe.show_alert({ message: __('تم إنشاء الفرع {0} بنجاح.', [created.branch]), indicator: 'green' });
			frappe.set_route('Form', 'Branch', created.branch);
		},
	});
}
