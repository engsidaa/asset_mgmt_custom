frappe.pages['asset-requisition-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('طلب أصل جديد'),
		single_column: true,
	});

	build_wizard(page);
};

async function get_my_branch() {
	try {
		const r = await frappe.db.get_list('Branch', {
			filters: { custom_branch_manager: frappe.session.user },
			fields: ['name'],
			limit: 2,
		});
		if (r && r.length === 1) return r[0].name;
	} catch (e) {
		// لا مشكلة — يختار المستخدم الفرع يدوياً
	}
	return null;
}

function build_wizard(page) {
	new asset_mgmt_custom.Wizard({
		wrapper: page.body,
		title: __('طلب أصل جديد'),
		subtitle: __('اطلب أصلاً جديداً لفرعك — سيمر الطلب على 3 مراحل اعتماد (المالية ثم مدير الفرع ثم إدارة الأصول)'),
		finish_label: __('إرسال الطلب'),
		steps: [
			{
				id: 'category',
				label: __('الفئة والكمية'),
				async render($body, wizard) {
					$body.append(`<label class="control-label">${__('فئة الأصل المطلوبة')} *</label>`);
					const category = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'asset_category', options: 'Asset Category', reqd: 1,
					}, 'asset_category');
					if (wizard.state.asset_category) category.set_value(wizard.state.asset_category);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('الصنف (اختياري)')}</label>`);
					const item = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'item_code', options: 'Item',
					}, 'item_code');
					if (wizard.state.item_code) item.set_value(wizard.state.item_code);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('الكمية')}</label>`);
					const qty = wizard.make_field($body, {
						fieldtype: 'Int', fieldname: 'quantity', default: 1,
					}, 'quantity');
					qty.set_value(wizard.state.quantity || 1);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('الفرع')} *</label>`);
					const branch = wizard.make_field($body, {
						fieldtype: 'Link', fieldname: 'branch', options: 'Branch', reqd: 1,
					}, 'branch');
					if (wizard.state.branch) {
						branch.set_value(wizard.state.branch);
					} else {
						const my_branch = await get_my_branch();
						if (my_branch) branch.set_value(my_branch);
					}
				},
				validate(wizard) {
					wizard.state.asset_category = wizard.controls.asset_category.get_value();
					wizard.state.item_code = wizard.controls.item_code.get_value();
					wizard.state.quantity = wizard.controls.quantity.get_value() || 1;
					wizard.state.branch = wizard.controls.branch.get_value();

					if (!wizard.state.asset_category) {
						wizard.show_error(__('يرجى اختيار فئة الأصل.'));
						return false;
					}
					if (!wizard.state.branch) {
						wizard.show_error(__('يرجى اختيار الفرع.'));
						return false;
					}
					return true;
				},
			},
			{
				id: 'context',
				label: __('طلبات معلَّقة'),
				async render($body, wizard) {
					$body.append(`<p class="text-muted">${__('قبل ما تكمل — دي الطلبات والأصول المعلَّقة بالفعل لنفس الفئة، تجنباً لتكرار طلب موجود أصلاً.')}</p>`);
					const $loading = $(`<div class="text-muted">${__('جارٍ التحميل...')}</div>`).appendTo($body);

					try {
						const ctx = await frappe.xcall(
							'asset_mgmt_custom.api.branch_manager.get_new_requisition_context',
							{ asset_category: wizard.state.asset_category }
						);
						$loading.remove();
						render_context($body, ctx);
					} catch (e) {
						$loading.text(__('تعذّر تحميل السياق — يمكنك المتابعة.'));
					}
				},
			},
			{
				id: 'details',
				label: __('التفاصيل'),
				render($body, wizard) {
					$body.append(`<label class="control-label">${__('الوصف')}</label>`);
					const description = wizard.make_field($body, { fieldtype: 'Text', fieldname: 'description' }, 'description');
					if (wizard.state.description) description.set_value(wizard.state.description);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('المبرر')}</label>`);
					const justification = wizard.make_field($body, { fieldtype: 'Text', fieldname: 'justification' }, 'justification');
					if (wizard.state.justification) justification.set_value(wizard.state.justification);

					$body.append(`<label class="control-label" style="margin-top:15px;">${__('التاريخ المطلوب')}</label>`);
					const required_by = wizard.make_field($body, { fieldtype: 'Date', fieldname: 'required_by' }, 'required_by');
					if (wizard.state.required_by) required_by.set_value(wizard.state.required_by);
				},
				validate(wizard) {
					wizard.state.description = wizard.controls.description.get_value();
					wizard.state.justification = wizard.controls.justification.get_value();
					wizard.state.required_by = wizard.controls.required_by.get_value();
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
								<div class="col-sm-6"><span class="label">${__('الفئة')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.asset_category)}</span></div>
								<div class="col-sm-6"><span class="label">${__('الفرع')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.branch)}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الكمية')}</span><br><span class="value">${wizard.state.quantity}</span></div>
								<div class="col-sm-6" style="margin-top:8px;"><span class="label">${__('الصنف')}</span><br><span class="value">${frappe.utils.escape_html(wizard.state.item_code || '—')}</span></div>
							</div>
						</div>
						<p class="text-muted">${__('سيبدأ الطلب في سلسلة الاعتماد فور الإرسال: المالية ← مدير الفرع ← إدارة الأصول.')}</p>
					`);
				},
			},
		],
		async finish(wizard) {
			const inserted = await frappe.xcall('frappe.client.insert', {
				doc: {
					doctype: 'Asset Requisition',
					asset_category: wizard.state.asset_category,
					item_code: wizard.state.item_code,
					quantity: wizard.state.quantity,
					branch: wizard.state.branch,
					description: wizard.state.description,
					justification: wizard.state.justification,
					required_by: wizard.state.required_by,
				},
			});

			const submitted = await frappe.xcall('frappe.client.submit', { doc: inserted });

			frappe.show_alert({ message: __('تم إرسال طلب الأصل بنجاح: {0}', [submitted.name]), indicator: 'green' });
			frappe.set_route('Form', 'Asset Requisition', submitted.name);
		},
	});
}

function render_context($body, ctx) {
	const pending = (ctx && ctx.pending_requisitions) || [];
	const assets = (ctx && ctx.pending_or_in_transit_assets) || [];

	if (!pending.length && !assets.length) {
		$body.append(`<div class="alert alert-success">${__('لا توجد طلبات أو أصول معلَّقة لنفس الفئة حالياً.')}</div>`);
		return;
	}

	if (pending.length) {
		$body.append(`<h6>${__('طلبات معلَّقة لنفس الفئة')}</h6>`);
		const $table = $(`<table class="table table-bordered" style="font-size:12px;"></table>`).appendTo($body);
		$table.append(`<thead><tr><th>${__('الطلب')}</th><th>${__('الكمية')}</th><th>${__('الحالة')}</th><th>${__('التاريخ')}</th></tr></thead>`);
		const $tbody = $(`<tbody></tbody>`).appendTo($table);
		pending.forEach((r) => {
			$tbody.append(`<tr><td>${frappe.utils.escape_html(r.name)}</td><td>${r.quantity}</td><td>${frappe.utils.escape_html(r.status)}</td><td>${frappe.utils.escape_html(r.request_date || '')}</td></tr>`);
		});
	}

	if (assets.length) {
		$body.append(`<h6 style="margin-top:15px;">${__('أصول قيد التفعيل/النقل لنفس الفئة')}</h6>`);
		const $table = $(`<table class="table table-bordered" style="font-size:12px;"></table>`).appendTo($body);
		$table.append(`<thead><tr><th>${__('الأصل')}</th><th>${__('الاسم')}</th><th>${__('الحالة')}</th></tr></thead>`);
		const $tbody = $(`<tbody></tbody>`).appendTo($table);
		assets.forEach((a) => {
			$tbody.append(`<tr><td>${frappe.utils.escape_html(a.name)}</td><td>${frappe.utils.escape_html(a.asset_name || '')}</td><td>${frappe.utils.escape_html(a.custom_operational_status || '')}</td></tr>`);
		});
	}
}
