frappe.pages['asset-depreciation-scenario-comparison'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('مقارنة سيناريوهات الإهلاك'),
		single_column: true,
	});

	new AssetDepreciationScenarioComparison(page);
};

const SCENARIO_FIELD_DEFS = [
	{
		fieldtype: 'Select',
		fieldname: 'depreciation_method',
		label: __('طريقة الإهلاك'),
		options: 'Straight Line\nWritten Down Value\nDouble Declining Balance',
		reqd: 1,
		default: 'Straight Line',
	},
	{ fieldtype: 'Int', fieldname: 'total_number_of_depreciations', label: __('عدد فترات الإهلاك'), reqd: 1, default: 60 },
	{ fieldtype: 'Int', fieldname: 'frequency_of_depreciation', label: __('التكرار (بالأشهر)'), reqd: 1, default: 1 },
	{ fieldtype: 'Currency', fieldname: 'expected_value_after_useful_life', label: __('القيمة المتبقية المتوقعة'), default: 0 },
	{ fieldtype: 'Percent', fieldname: 'rate_of_depreciation', label: __('معدل الإهلاك % (للقسط المتناقص فقط)') },
	{ fieldtype: 'Date', fieldname: 'depreciation_start_date', label: __('تاريخ بدء الإهلاك (اختياري)') },
];

class AssetDepreciationScenarioComparison {
	constructor(page) {
		this.page = page;
		this.render();
	}

	render() {
		this.page.body.empty();

		const $wrap = $(`
			<div class="amc-depr-compare" style="max-width:960px; margin:20px auto;">
				<p class="text-muted">${__('محاكاة جدول إهلاك بديل (طريقة/معدل/عمر إنتاجي مختلف) لأصل موجود فعلاً — للمقارنة فقط، بلا أي تعديل على الأصل أو جدول الإهلاك الفعلي.')}</p>
				<div class="amc-asset-field" style="max-width:400px; margin-bottom:16px;"></div>
				<div style="display:flex; gap:24px;">
					<div class="amc-scenario-col" data-key="a" style="flex:1; border:1px solid var(--border-color,#ddd); border-radius:6px; padding:12px;">
						<h5>${__('السيناريو أ')}</h5>
						<div class="amc-scenario-fields"></div>
					</div>
					<div class="amc-scenario-col" data-key="b" style="flex:1; border:1px solid var(--border-color,#ddd); border-radius:6px; padding:12px;">
						<h5>${__('السيناريو ب')}</h5>
						<div class="amc-scenario-fields"></div>
					</div>
				</div>
				<button class="btn btn-primary btn-sm amc-compare-btn" style="margin-top:16px;">${__('قارن السيناريوهين')}</button>
				<div class="amc-results" style="margin-top:24px;"></div>
			</div>
		`).appendTo(this.page.body);

		this.asset_control = frappe.ui.form.make_control({
			parent: $wrap.find('.amc-asset-field').get(0),
			df: {
				fieldtype: 'Link',
				fieldname: 'asset',
				label: __('الأصل'),
				options: 'Asset',
				reqd: 1,
				get_query: () => ({ filters: { docstatus: 1 } }),
			},
			render_input: true,
		});
		this.asset_control.refresh();

		this.scenario_controls = { a: {}, b: {} };
		for (const key of ['a', 'b']) {
			const $container = $wrap.find(`.amc-scenario-col[data-key="${key}"] .amc-scenario-fields`);
			for (const df of SCENARIO_FIELD_DEFS) {
				const $field_wrap = $('<div style="margin-bottom:8px;"></div>').appendTo($container);
				const control = frappe.ui.form.make_control({
					parent: $field_wrap.get(0),
					df,
					render_input: true,
				});
				control.refresh();
				if (df.default !== undefined) control.set_value(df.default);
				this.scenario_controls[key][df.fieldname] = control;
			}
		}

		this.$results = $wrap.find('.amc-results');
		$wrap.find('.amc-compare-btn').on('click', () => this.compare());
	}

	collect_scenario(key, label) {
		const values = { label };
		for (const [fieldname, control] of Object.entries(this.scenario_controls[key])) {
			values[fieldname] = control.get_value();
		}
		return values;
	}

	async compare() {
		const asset = this.asset_control.get_value();
		if (!asset) {
			frappe.show_alert({ message: __('اختر الأصل أولاً.'), indicator: 'orange' });
			return;
		}

		const scenarios = [
			this.collect_scenario('a', __('السيناريو أ')),
			this.collect_scenario('b', __('السيناريو ب')),
		];

		this.$results.html(`<div class="text-muted">${__('جارٍ الحساب...')}</div>`);
		try {
			const data = await frappe.xcall('asset_mgmt_custom.depreciation_scenarios.compare_scenarios', {
				asset,
				scenarios,
			});
			this.render_results(data);
		} catch (e) {
			this.$results.html(`<div class="text-danger">${frappe.utils.escape_html(e.message || __('حدث خطأ أثناء الحساب.'))}</div>`);
		}
	}

	render_results(data) {
		const fmt_currency = (v) => format_currency(v, null);

		let summary_html = `
			<div style="margin-bottom:8px;"><b>${__('الأصل')}:</b> ${data.asset} — ${frappe.utils.escape_html(data.asset_name || '')}
			&nbsp; <b>${__('التكلفة الإجمالية')}:</b> ${fmt_currency(data.gross_purchase_amount)}</div>
			<table class="table table-bordered" style="margin-top:8px;">
				<thead><tr>
					<th>${__('السيناريو')}</th>
					<th>${__('الطريقة')}</th>
					<th>${__('عدد الفترات')}</th>
					<th>${__('إجمالي الإهلاك')}</th>
					<th>${__('القيمة الدفترية النهائية')}</th>
				</tr></thead>
				<tbody>
		`;
		for (const s of data.scenarios) {
			summary_html += `
				<tr>
					<td><b>${frappe.utils.escape_html(s.label)}</b></td>
					<td>${frappe.utils.escape_html(s.depreciation_method)}</td>
					<td>${s.number_of_periods}</td>
					<td>${fmt_currency(s.total_depreciation)}</td>
					<td>${fmt_currency(s.final_book_value)}</td>
				</tr>
			`;
		}
		summary_html += '</tbody></table>';

		let schedules_html = '<div style="display:flex; gap:24px; margin-top:16px;">';
		for (const s of data.scenarios) {
			schedules_html += `
				<div style="flex:1; max-height:400px; overflow-y:auto;">
					<h6>${frappe.utils.escape_html(s.label)}</h6>
					<table class="table table-bordered table-sm">
						<thead><tr><th>${__('التاريخ')}</th><th>${__('قسط الإهلاك')}</th><th>${__('المتراكم')}</th></tr></thead>
						<tbody>
							${s.schedule.map((row) => `
								<tr>
									<td>${row.schedule_date}</td>
									<td>${fmt_currency(row.depreciation_amount)}</td>
									<td>${fmt_currency(row.accumulated_depreciation_amount)}</td>
								</tr>
							`).join('')}
						</tbody>
					</table>
				</div>
			`;
		}
		schedules_html += '</div>';

		this.$results.html(summary_html + schedules_html);
	}
}
