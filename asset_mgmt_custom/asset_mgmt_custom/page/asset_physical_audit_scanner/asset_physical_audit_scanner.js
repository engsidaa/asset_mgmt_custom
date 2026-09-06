frappe.pages['asset-physical-audit-scanner'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('مسح الجرد المادي بالباركود'),
		single_column: true,
	});

	new AssetPhysicalAuditScanner(page);
};

class AssetPhysicalAuditScanner {
	constructor(page) {
		this.page = page;
		this.audit = null;
		this.render_picker();
	}

	render_picker() {
		this.page.body.empty();
		const $wrap = $(`
			<div class="amc-scanner-picker" style="max-width:520px; margin:24px auto;">
				<p class="text-muted">${__('اختر جرداً قائماً (مسودة) لمتابعة المسح، أو أنشئ جرداً جديداً لفرع.')}</p>
				<div class="picker-field" style="margin-bottom:12px;"></div>
				<button class="btn btn-primary btn-sm amc-open-audit" style="margin-inline-end:8px;">${__('فتح الجرد')}</button>
				<button class="btn btn-default btn-sm amc-new-audit">${__('+ جرد جديد')}</button>
			</div>
		`).appendTo(this.page.body);

		const control = frappe.ui.form.make_control({
			parent: $wrap.find('.picker-field').get(0),
			df: {
				fieldtype: 'Link',
				fieldname: 'audit',
				label: __('جرد قائم (مسودة)'),
				options: 'Asset Physical Audit',
				get_query: () => ({ filters: { docstatus: 0 } }),
			},
			render_input: true,
		});
		control.refresh();

		$wrap.find('.amc-open-audit').on('click', async () => {
			const name = control.get_value();
			if (!name) {
				frappe.show_alert({ message: __('اختر جرداً أولاً.'), indicator: 'orange' });
				return;
			}
			await this.load_audit(name);
		});

		$wrap.find('.amc-new-audit').on('click', () => this.prompt_new_audit());
	}

	prompt_new_audit() {
		frappe.prompt(
			[
				{
					fieldtype: 'Link',
					fieldname: 'cost_center',
					label: __('الفرع (مركز التكلفة)'),
					options: 'Cost Center',
					reqd: 1,
				},
			],
			async (values) => {
				frappe.show_alert({ message: __('جارٍ إنشاء الجرد وتحميل الأصول المتوقعة...'), indicator: 'blue' });
				const doc = await frappe.db.insert({
					doctype: 'Asset Physical Audit',
					cost_center: values.cost_center,
					audited_by: frappe.session.user,
				});
				await frappe.xcall('run_doc_method', {
					dt: 'Asset Physical Audit',
					dn: doc.name,
					method: 'fetch_assets',
				});
				await this.load_audit(doc.name);
			},
			__('جرد مادي جديد'),
			__('إنشاء وبدء المسح')
		);
	}

	async load_audit(name) {
		this.audit = await frappe.db.get_doc('Asset Physical Audit', name);
		if (this.audit.docstatus !== 0) {
			frappe.msgprint(__('هذا الجرد ليس في حالة مسودة — لا يمكن متابعة المسح عليه.'));
			return;
		}
		this.render_scanner();
	}

	render_scanner() {
		this.page.body.empty();
		this.log_rows = [];

		const $wrap = $(`
			<div class="amc-scanner" style="max-width:640px; margin:24px auto;">
				<div class="amc-scanner-summary" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
					<div>
						<b>${__('الجرد')}:</b> ${this.audit.name} &mdash; ${frappe.utils.escape_html(this.audit.cost_center)}
					</div>
					<div class="amc-counts" style="font-size:16px;"></div>
				</div>
				<input type="text" class="form-control amc-scan-input" placeholder="${__('امسح الباركود/QR أو اكتب الكود ثم اضغط Enter')}" style="font-size:18px; padding:10px;" autofocus>
				<div class="amc-scan-log" style="margin-top:16px; max-height:360px; overflow-y:auto;"></div>
				<div style="margin-top:20px; display:flex; justify-content:space-between;">
					<a class="amc-back" href="#">${__('&larr; اختيار جرد آخر')}</a>
					<button class="btn btn-success btn-sm amc-finish">${__('إنهاء وتسليم الجرد')}</button>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$input = $wrap.find('.amc-scan-input');
		this.$counts = $wrap.find('.amc-counts');
		this.$log = $wrap.find('.amc-scan-log');
		this.update_counts();

		this.$input.on('keydown', (ev) => {
			if (ev.key === 'Enter') {
				ev.preventDefault();
				const value = this.$input.val().trim();
				if (value) this.scan(value);
				this.$input.val('');
			}
		});
		this.$input.trigger('focus');

		$wrap.find('.amc-back').on('click', (ev) => {
			ev.preventDefault();
			this.render_picker();
		});

		$wrap.find('.amc-finish').on('click', () => this.finish_audit());
	}

	update_counts() {
		this.$counts.html(
			`<span class="indicator-pill green">${__('موجود')}: ${this.audit.found_count || 0}</span>` +
			`&nbsp;/&nbsp;${this.audit.total_assets || 0} ${__('إجمالي')}`
		);
	}

	async scan(identifier) {
		try {
			const data = await frappe.xcall('run_doc_method', {
				dt: 'Asset Physical Audit',
				dn: this.audit.name,
				method: 'scan_mark_found',
				args: { identifier },
			});
			this.audit.found_count = data.found_count;
			this.audit.total_assets = data.total_assets;
			this.update_counts();
			this.add_log_row({
				ok: true,
				text: data.was_unexpected
					? __('{0} — أصل غير متوقع بهذا الموقع، أُضيف للجرد وعُلِّم موجوداً', [data.asset_name || data.asset])
					: __('{0} — تم تعليمه موجوداً', [data.asset_name || data.asset]),
			});
		} catch (e) {
			this.add_log_row({ ok: false, text: identifier + ' — ' + (e.message || __('كود غير معروف')) });
		}
		this.$input.trigger('focus');
	}

	add_log_row({ ok, text }) {
		const $row = $(`
			<div class="amc-scan-row" style="padding:8px 10px; border-inline-start:3px solid ${ok ? '#2ecc71' : '#e74c3c'}; background:${ok ? '#f4fdf7' : '#fdf4f4'}; margin-bottom:6px; border-radius:2px;">
				${frappe.utils.escape_html(text)}
			</div>
		`);
		this.$log.prepend($row);
	}

	async finish_audit() {
		frappe.confirm(
			__('سيتم تسليم الجرد نهائياً — الأصول التي لم تُمسح تبقى بلا حالة (لا تُعتبر مفقودة تلقائياً). متابعة؟'),
			async () => {
				await frappe.xcall(
					'asset_mgmt_custom.asset_mgmt_custom.doctype.asset_physical_audit.asset_physical_audit.submit_audit',
					{ audit_name: this.audit.name }
				);
				frappe.show_alert({ message: __('تم تسليم الجرد بنجاح.'), indicator: 'green' });
				frappe.set_route('Form', 'Asset Physical Audit', this.audit.name);
			}
		);
	}
}
