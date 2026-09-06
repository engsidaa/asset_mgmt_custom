frappe.pages['asset-360-cockpit'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('لوحة أصل 360°'),
		single_column: true,
	});

	new Asset360Cockpit(page);
};

class Asset360Cockpit {
	constructor(page) {
		this.page = page;
		this.render_picker();
	}

	render_picker() {
		this.page.body.empty();
		const $wrap = $(`
			<div class="amc-cockpit-picker" style="max-width:420px; margin:24px auto;">
				<p class="text-muted">${__('اختر أصلاً لعرض كل ما يخصه الآن في شاشة واحدة — مكمِّلة لسجل التدقيق الكامل (الذي يعرض التاريخ فقط).')}</p>
				<div class="picker-field"></div>
			</div>
		`).appendTo(this.page.body);

		const control = frappe.ui.form.make_control({
			parent: $wrap.find('.picker-field').get(0),
			df: {
				fieldtype: 'Link',
				fieldname: 'asset',
				label: __('الأصل'),
				options: 'Asset',
				get_query: () => ({ filters: { docstatus: 1 } }),
				onchange: () => {
					const asset = control.get_value();
					if (asset) this.load(asset);
				},
			},
			render_input: true,
		});
		control.refresh();
	}

	async load(asset) {
		this.page.body.html(`<div class="text-muted" style="margin:24px;">${__('جارٍ التحميل...')}</div>`);
		let data;
		try {
			data = await frappe.xcall('asset_mgmt_custom.api.branch_manager.get_asset_detail', { asset });
		} catch (e) {
			this.render_picker();
			frappe.show_alert({ message: e.message || __('تعذّر تحميل بيانات الأصل.'), indicator: 'red' });
			return;
		}
		this.render_cockpit(asset, data);
	}

	render_cockpit(asset, data) {
		const a = data.asset;
		const fmt_currency = (v) => format_currency(v, null);
		const fmt_date = (v) => (v ? frappe.datetime.str_to_user(v) : '—');

		const ahi = a.custom_ahi_score;
		const ahi_color = ahi == null ? '#999' : ahi >= 70 ? '#2ecc71' : ahi >= 40 ? '#f39c12' : '#e74c3c';
		const criticality_colors = { 'Critical': '#e74c3c', 'High': '#f39c12', 'Medium': '#3498db', 'Low': '#95a5a6' };

		this.page.body.empty();
		const $wrap = $(`
			<div class="amc-cockpit" style="max-width:1000px; margin:20px auto;">
				<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
					<div>
						<div style="font-size:20px; font-weight:bold;">${frappe.utils.escape_html(a.asset_name || asset)}</div>
						<div class="text-muted">${asset} — ${frappe.utils.escape_html(a.asset_category || '')} — ${frappe.utils.escape_html(a.custom_branch || '')}</div>
					</div>
					<div>
						<a class="btn btn-default btn-sm amc-back" href="#">${__('← أصل آخر')}</a>
						<a class="btn btn-default btn-sm" href="/app/asset/${asset}" target="_blank">${__('فتح النموذج الكامل')}</a>
					</div>
				</div>

				<div class="amc-kpi-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:20px;">
					${this.kpi_card(__('الحالة'), a.status)}
					${this.kpi_card(__('الحالة التشغيلية'), a.custom_operational_status)}
					${this.kpi_card(__('مؤشر صحة الأصل (AHI)'), ahi != null ? ahi + '%' : '—', ahi_color)}
					${this.kpi_card(__('العمر المتبقي (شهر)'), a.custom_rul_months != null ? a.custom_rul_months : '—')}
					${this.kpi_card(__('الحرجية'), a.criticality_level || __('غير مقيَّم'), criticality_colors[a.criticality_level])}
					${this.kpi_card(__('الضمان'), a.custom_under_warranty ? __('سارٍ حتى {0}', [fmt_date(a.custom_warranty_expiry)]) : __('منتهٍ/غير محدَّد'))}
				</div>

				<div class="amc-kpi-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:24px;">
					${this.kpi_card(__('التكلفة الإجمالية للملكية'), fmt_currency(a.custom_tco))}
					${this.kpi_card(__('التكلفة السنوية'), fmt_currency(a.custom_annual_tco))}
					${this.kpi_card(__('التوصية'), a.custom_tco_recommendation || '—', a.custom_tco_is_outlier ? '#e74c3c' : null)}
					${this.kpi_card(__('إجمالي تكلفة الصيانة'), fmt_currency(a.custom_total_maintenance_cost))}
				</div>

				<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
					<div>
						<h5>${__('أوامر العمل المفتوحة')} (${data.open_work_orders.length})</h5>
						${this.simple_table(
							['الأولوية', 'النوع', 'الحالة', 'تاريخ الطلب'],
							data.open_work_orders.map((w) => [w.priority, w.work_type, w.status, fmt_date(w.request_date)]),
							__('لا توجد أوامر عمل مفتوحة.')
						)}
					</div>
					<div>
						<h5>${__('مهام الصيانة الوقائية')}</h5>
						${this.simple_table(
							['المهمة', 'الدورية', 'الاستحقاق القادم'],
							data.maintenance_tasks.map((t) => [t.maintenance_task, t.periodicity, fmt_date(t.next_due_date)]),
							__('لا توجد مهام صيانة وقائية مجدولة.')
						)}
					</div>
				</div>

				<div style="margin-top:20px;">
					<h5>${__('آخر فحص سلامة')}</h5>
					${data.asset.last_safety_inspection
						? `<p>${fmt_date(data.asset.last_safety_inspection.inspection_date)} — ${__('النتيجة')}: <b>${frappe.utils.escape_html(data.asset.last_safety_inspection.overall_result || '')}</b> — ${__('القادم')}: ${fmt_date(data.asset.last_safety_inspection.next_inspection_date)}</p>`
						: `<p class="text-muted">${__('لا يوجد فحص سلامة مُسجَّل.')}</p>`
					}
				</div>
			</div>
		`).appendTo(this.page.body);

		$wrap.find('.amc-back').on('click', (ev) => {
			ev.preventDefault();
			this.render_picker();
		});
	}

	kpi_card(label, value, color) {
		return `
			<div style="border:1px solid var(--border-color,#e5e5e5); border-radius:6px; padding:10px 12px;">
				<div class="text-muted" style="font-size:11px;">${label}</div>
				<div style="font-size:16px; font-weight:bold; ${color ? `color:${color};` : ''}">${frappe.utils.escape_html(String(value ?? '—'))}</div>
			</div>
		`;
	}

	simple_table(headers, rows, empty_label) {
		if (!rows.length) {
			return `<p class="text-muted">${empty_label}</p>`;
		}
		return `
			<table class="table table-bordered table-sm">
				<thead><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr></thead>
				<tbody>
					${rows.map((r) => `<tr>${r.map((c) => `<td>${frappe.utils.escape_html(String(c ?? '—'))}</td>`).join('')}</tr>`).join('')}
				</tbody>
			</table>
		`;
	}
}
