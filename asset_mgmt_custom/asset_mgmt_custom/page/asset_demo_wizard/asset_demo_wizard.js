frappe.pages['asset-demo-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('معالج البيانات التجريبية'),
		single_column: true,
	});

	new AssetDemoWizard(page);
};

class AssetDemoWizard {
	constructor(page) {
		this.page = page;
		this.steps = [];
		this.running = false;

		this.page.set_indicator(__('أداة لمدير النظام فقط'), 'orange');

		this.page.add_button(__('١. تجهيز الحسابات الأساسية'), () => this.run_bootstrap(), { icon: 'setting' });
		this.page.add_button(__('٢. تشغيل كل الخطوات'), () => this.run_all(), { icon: 'play' });
		this.page.add_button(__('٣. تقرير التغطية'), () => this.show_coverage(), { icon: 'small-file' });
		this.page.add_button(__('٤. تشغيل كل التقارير'), () => this.run_all_reports(), { icon: 'file' });
		this.page.add_button(__('٥. حذف كل البيانات التجريبية'), () => this.confirm_cleanup(), {
			icon: 'delete',
		}).addClass('btn-danger');

		this.$body = $(`
			<div dir="rtl" style="max-width: 960px;">
				<div class="alert alert-warning">
					${__('هذه الأداة تُنشئ بيانات تجريبية حقيقية وباقية في قاعدة البيانات (وليست مؤقتة). ' +
						'كل مستند تُنشئه هذه الأداة يُسجَّل تلقائياً، ويمكن حذفه بالكامل بأمان في أي وقت ' +
						'بزر "حذف كل البيانات التجريبية" أعلاه — دون المساس بأي بيانات حقيقية أخرى.')}
				</div>
				<div class="demo-summary text-muted" style="margin-bottom: 15px;"></div>
				<div class="demo-steps"></div>
				<h5 style="margin-top: 25px;">${__('سجل التنفيذ')}</h5>
				<div class="demo-console" style="
					background: var(--fg-color, #1e1e1e); color: #ddd; font-family: monospace;
					font-size: 12px; padding: 12px; border-radius: 6px; height: 320px;
					overflow-y: auto; white-space: pre-wrap;"></div>
			</div>
		`).appendTo(this.page.body);

		this.$steps = this.$body.find('.demo-steps');
		this.$console = this.$body.find('.demo-console');
		this.$summary = this.$body.find('.demo-summary');

		this.load_steps();
		this.refresh_summary();
	}

	load_steps() {
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.get_steps',
			callback: (r) => {
				this.steps = r.message || [];
				this.render_steps();
			},
		});
	}

	render_steps() {
		this.$steps.empty();
		const groups = {};
		this.steps.forEach((s) => {
			groups[s.group] = groups[s.group] || [];
			groups[s.group].push(s);
		});

		Object.keys(groups).forEach((group) => {
			const $group = $(`<div style="margin-bottom: 18px;">
				<h6 style="color: var(--text-muted);">${frappe.utils.escape_html(group)}</h6>
			</div>`).appendTo(this.$steps);

			groups[group].forEach((step) => {
				const $row = $(`
					<div class="d-flex align-items-center justify-content-between step-row"
						data-step="${step.id}"
						style="padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; margin-bottom: 6px;">
						<span>${frappe.utils.escape_html(step.title)}</span>
						<button class="btn btn-xs btn-default run-step-btn">${__('تشغيل')}</button>
					</div>
				`).appendTo($group);

				$row.find('.run-step-btn').on('click', () => this.run_step(step));
			});
		});
	}

	log(level, text) {
		const colors = { ok: '#4caf50', fail: '#f44336', skip: '#9e9e9e', info: '#42a5f5' };
		const icons = { ok: '✅', fail: '❌', skip: '⏭️', info: 'ℹ️' };
		const line = $('<div></div>')
			.css('color', colors[level] || '#ddd')
			.text(`${icons[level] || ''} ${text}`);
		this.$console.append(line);
		this.$console.scrollTop(this.$console[0].scrollHeight);
	}

	log_header(text) {
		this.$console.append(
			$('<div></div>').css({ color: '#fff', 'font-weight': 'bold', 'margin-top': '10px' }).text('▶ ' + text)
		);
		this.$console.scrollTop(this.$console[0].scrollHeight);
	}

	run_step(step, silent) {
		if (this.running) return Promise.resolve();
		this.running = true;
		if (!silent) this.log_header(step.title);

		return new Promise((resolve) => {
			frappe.call({
				method: 'asset_mgmt_custom.setup.demo_wizard.run_step',
				args: { step_id: step.id },
				freeze: true,
				freeze_message: __('جارٍ التنفيذ: {0}', [step.title]),
				callback: (r) => {
					const lines = (r.message && r.message.lines) || [];
					lines.forEach((l) => this.log(l.level, l.text));
					if (!lines.length) this.log('info', __('لا توجد نتائج لهذه الخطوة.'));
					this.refresh_summary();
				},
				always: () => {
					this.running = false;
					resolve();
				},
			});
		});
	}

	async run_all() {
		if (this.running) return;
		this.log_header(__('تشغيل كل الخطوات بالترتيب...'));
		for (const step of this.steps) {
			await this.run_step(step, true);
		}
		this.log_header(__('انتهى تشغيل كل الخطوات.'));
		frappe.show_alert({ message: __('تم الانتهاء من كل الخطوات.'), indicator: 'green' });
		this.show_coverage();
	}

	show_coverage() {
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.coverage_report',
			freeze: true,
			freeze_message: __('جارٍ فحص التغطية...'),
			callback: (r) => {
				const rep = r.message || { total_doctypes: 0, covered: [], missing: [] };
				this.log_header(__('تقرير التغطية: {0} من {1} نوع مستند تم اختباره',
					[rep.covered.length, rep.total_doctypes]));

				if (rep.missing.length) {
					this.log('fail', __('لم يتم اختبار {0} نوع مستند إطلاقاً:', [rep.missing.length]));
					rep.missing.forEach((m) => this.log('fail', `  — ${m.doctype}`));
				} else {
					this.log('ok', __('كل أنواع المستندات في التطبيق تم اختبارها مرة واحدة على الأقل.'));
				}

				const low = rep.covered.filter((c) => c.count === 1);
				if (low.length) {
					this.log('info', __('{0} نوع تم اختباره بسيناريو واحد فقط (شكل واحد) — راجعها لو عايز '
						+ 'سيناريوهات متعددة (نجاح/فشل، اعتماد/رفض، إلخ):', [low.length]));
					low.forEach((c) => this.log('info', `  — ${c.doctype}`));
				}
			},
		});
	}

	run_bootstrap() {
		this.log_header(__('تجهيز الحسابات الأساسية...'));
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.run_bootstrap',
			freeze: true,
			freeze_message: __('جارٍ تجهيز الحسابات الأساسية...'),
			callback: (r) => {
				const lines = (r.message && r.message.lines) || [];
				lines.forEach((l) => this.log(l.level, l.text));
				this.log_header(__('انتهى تجهيز الحسابات الأساسية.'));
			},
		});
	}

	run_all_reports() {
		this.log_header(__('تشغيل كل التقارير...'));
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.run_all_reports',
			freeze: true,
			freeze_message: __('جارٍ تشغيل كل التقارير...'),
			callback: (r) => {
				const lines = (r.message && r.message.lines) || [];
				lines.forEach((l) => this.log(l.level, l.text));
				this.log_header(__('انتهى تشغيل التقارير.'));
			},
		});
	}

	refresh_summary() {
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.get_summary',
			callback: (r) => {
				const s = r.message || { total: 0, by_doctype: [] };
				if (!s.total) {
					this.$summary.html(__('لا توجد أي بيانات تجريبية حالياً.'));
					return;
				}
				const parts = s.by_doctype.map((d) => `${d.reference_doctype} (${d.cnt})`).join('، ');
				this.$summary.html(
					`<b>${__('إجمالي البيانات التجريبية الحالية')}:</b> ${s.total} — ${parts}`
				);
			},
		});
	}

	confirm_cleanup() {
		frappe.confirm(
			__('سيتم حذف كل البيانات التجريبية التي أنشأتها هذه الأداة نهائياً من قاعدة البيانات. ' +
				'لن تتأثر أي بيانات حقيقية أخرى. هل أنت متأكد؟'),
			() => this.cleanup(),
		);
	}

	cleanup() {
		this.log_header(__('حذف كل البيانات التجريبية...'));
		frappe.call({
			method: 'asset_mgmt_custom.setup.demo_wizard.cleanup_all',
			freeze: true,
			freeze_message: __('جارٍ الحذف...'),
			callback: (r) => {
				const lines = (r.message && r.message.lines) || [];
				lines.forEach((l) => this.log(l.level, l.text));
				this.log_header(__('انتهى الحذف.'));
				this.refresh_summary();
				frappe.show_alert({ message: __('تم حذف البيانات التجريبية.'), indicator: 'green' });
			},
		});
	}
}
