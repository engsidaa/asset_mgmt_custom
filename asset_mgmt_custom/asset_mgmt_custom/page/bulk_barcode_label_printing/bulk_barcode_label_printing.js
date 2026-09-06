frappe.pages['bulk-barcode-label-printing'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('طباعة ملصقات الباركود دفعة واحدة'),
		single_column: true,
	});

	build_page(page);
};

function build_page(page) {
	const $wrap = $(`
		<div class="amc-bulk-labels" style="max-width:520px; margin:24px auto;">
			<p class="text-muted">${__('يُنشئ ملف PDF واحد يجمع ملصق باركود لكل أصل مطابق للفلاتر أدناه — بدل فتح كل أصل وطباعة ملصقه بمفرده.')}</p>
			<div class="field-branch" style="margin-bottom:12px;"></div>
			<div class="field-category" style="margin-bottom:12px;"></div>
			<div class="field-uncoded-only" style="margin-bottom:16px;"></div>
			<button class="btn btn-primary btn-sm amc-generate">${__('إنشاء ملف الملصقات (PDF)')}</button>
			<div class="amc-result" style="margin-top:16px;"></div>
		</div>
	`).appendTo(page.body);

	const branch = frappe.ui.form.make_control({
		parent: $wrap.find('.field-branch').get(0),
		df: { fieldtype: 'Link', fieldname: 'branch', label: __('الفرع (اختياري)'), options: 'Branch' },
		render_input: true,
	});
	branch.refresh();

	const category = frappe.ui.form.make_control({
		parent: $wrap.find('.field-category').get(0),
		df: { fieldtype: 'Link', fieldname: 'asset_category', label: __('فئة الأصل (اختياري)'), options: 'Asset Category' },
		render_input: true,
	});
	category.refresh();

	const uncoded_only = frappe.ui.form.make_control({
		parent: $wrap.find('.field-uncoded-only').get(0),
		df: { fieldtype: 'Check', fieldname: 'uncoded_only', label: __('الأصول غير المُرمَّزة فقط'), default: 1 },
		render_input: true,
	});
	uncoded_only.refresh();
	uncoded_only.set_value(1);

	const $result = $wrap.find('.amc-result');

	$wrap.find('.amc-generate').on('click', async () => {
		const filters = { docstatus: 1 };
		if (branch.get_value()) filters.custom_branch = branch.get_value();
		if (category.get_value()) filters.asset_category = category.get_value();
		if (uncoded_only.get_value()) filters.custom_coding_status = ['!=', 'Coded'];

		$result.html(`<div class="text-muted">${__('جارٍ البحث عن الأصول المطابقة...')}</div>`);
		const assets = await frappe.db.get_list('Asset', { filters, fields: ['name'], limit: 0 });
		if (!assets.length) {
			$result.html(`<div class="text-muted">${__('لا توجد أصول مطابقة للفلاتر المحددة.')}</div>`);
			return;
		}

		$result.html(`<div class="text-muted">${__('جارٍ إنشاء ملف PDF لـ {0} أصل...', [assets.length])}</div>`);
		const names = assets.map((a) => a.name);

		const r = await frappe.call({
			method: 'frappe.utils.print_format.download_multi_pdf_async',
			args: {
				doctype: 'Asset',
				name: JSON.stringify(names),
				format: 'Asset Barcode Label',
				no_letterhead: '1',
			},
		});

		const task_id = r.message.task_id;
		frappe.realtime.task_subscribe(task_id);
		frappe.realtime.on(`task_complete:${task_id}`, (data) => {
			$result.html(
				`<a class="btn btn-success btn-sm" href="${data.file_url}" target="_blank">${__('تحميل ملف الملصقات ({0} أصل)', [names.length])}</a>`
			);
			frappe.realtime.task_unsubscribe(task_id);
			frappe.realtime.off(`task_complete:${task_id}`);
		});
	});
}
