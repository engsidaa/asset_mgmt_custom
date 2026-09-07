frappe.pages['it-support-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('لوحة دعم تقنية المعلومات'),
		single_column: true,
	});

	new ITSupportDashboard(page);
};

class ITSupportDashboard {
	constructor(page) {
		this.page = page;
		this.page.set_primary_action(__('تحديث'), () => this.load(), 'refresh');
		this.load();
	}

	async load() {
		this.page.body.html(`<div class="text-muted" style="margin:24px;">${__('جارٍ التحميل...')}</div>`);
		let data;
		try {
			data = await frappe.xcall('asset_mgmt_custom.api.it_dashboard.get_it_dashboard_summary');
		} catch (e) {
			this.page.body.html(`<div class="text-muted" style="margin:24px;">${__('تعذّر تحميل البيانات.')}</div>`);
			frappe.show_alert({ message: e.message || __('حدث خطأ.'), indicator: 'red' });
			return;
		}
		this.render(data);
	}

	render(d) {
		const fmt_date = (v) => (v ? frappe.datetime.str_to_user(v) : '—');

		this.page.body.empty();
		const $wrap = $(`
			<div class="it-dashboard" style="max-width:1000px; margin:20px auto;">
				<div class="it-kpi-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px;">
					${this.kpi_card(__('شكاوى IT مفتوحة'), d.open_it_complaints, '#3498db')}
					${this.kpi_card(__('متأخرة عن SLA'), d.overdue_it_complaints, d.overdue_it_complaints ? '#e74c3c' : null)}
					${this.kpi_card(__('تعطيل كامل مفتوح'), d.full_outage_open, d.full_outage_open ? '#e74c3c' : null)}
					${this.kpi_card(__('صيانة عامة مفتوحة (للمقارنة)'), d.open_general_complaints)}
				</div>

				<div class="it-kpi-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:24px;">
					${this.kpi_card(__('متوسط زمن الحل — IT (ساعة، آخر 90 يوم)'), d.avg_resolution_hours_it ?? '—')}
					${this.kpi_card(__('متوسط زمن الحل — غير IT (ساعة، آخر 90 يوم)'), d.avg_resolution_hours_other ?? '—')}
				</div>

				<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
					<div>
						<h5>${__('أكثر أنواع الأجهزة تكراراً (آخر 90 يوم)')}</h5>
						${this.simple_table(
							[__('نوع الجهاز'), __('العدد')],
							(d.top_device_types || []).map((t) => [t.it_device_type, t.total]),
							__('لا توجد بيانات كافية بعد.')
						)}
					</div>
					<div>
						<h5>${__('تراخيص برامج تقترب من الانتهاء (٣٠ يوماً القادمة)')}</h5>
						${this.simple_table(
							[__('البرنامج'), __('المورِّد'), __('الجهاز'), __('تاريخ الانتهاء')],
							(d.expiring_licenses || []).map((l) => [
								`<a href="/app/asset-software-license/${encodeURIComponent(l.name)}">${frappe.utils.escape_html(l.software_name || l.name)}</a>`,
								frappe.utils.escape_html(l.vendor || '—'),
								frappe.utils.escape_html(l.asset_name || '—'),
								frappe.utils.escape_html(fmt_date(l.expiry_date)),
							]),
							__('لا توجد تراخيص مقتربة من الانتهاء.'),
							true
						)}
					</div>
				</div>

				<div style="margin-top:20px;">
					<a class="btn btn-default btn-sm" href="/app/asset-work-order?complaint_department=${encodeURIComponent('تقنية المعلومات')}" target="_blank">
						${__('فتح كل شكاوى تقنية المعلومات')}
					</a>
				</div>
			</div>
		`).appendTo(this.page.body);
	}

	kpi_card(label, value, color) {
		return `
			<div style="border:1px solid var(--border-color,#e5e5e5); border-radius:6px; padding:10px 12px;">
				<div class="text-muted" style="font-size:11px;">${label}</div>
				<div style="font-size:16px; font-weight:bold; ${color ? `color:${color};` : ''}">${frappe.utils.escape_html(String(value ?? '—'))}</div>
			</div>
		`;
	}

	simple_table(headers, rows, empty_label, allow_html) {
		if (!rows.length) {
			return `<p class="text-muted">${empty_label}</p>`;
		}
		const cell = (c) => (allow_html ? c ?? '—' : frappe.utils.escape_html(String(c ?? '—')));
		return `
			<table class="table table-bordered table-sm">
				<thead><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr></thead>
				<tbody>
					${rows.map((r) => `<tr>${r.map((c) => `<td>${cell(c)}</td>`).join('')}</tr>`).join('')}
				</tbody>
			</table>
		`;
	}
}
