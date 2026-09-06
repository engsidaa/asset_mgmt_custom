/**
 * إطار عمل مشترك لكل صفحات الويزارد (خطوات) في هذا التطبيق — بدل تكرار
 * منطق التنقل بين الخطوات وشريط التقدم في كل صفحة على حدة. كل صفحة
 * ويزارد (Asset Work Order / Asset Requisition / إتمام أمر عمل / ترميز
 * أصل) تبني نفس الشكل والسلوك، وتُعرِّف فقط خطواتها الخاصة.
 *
 * استخدام كل خطوة:
 *   {
 *     id: "asset",
 *     label: "اختر الأصل",
 *     render(container, wizard) { ... تبني الحقول داخل container ... },
 *     validate(wizard) { return true/false or a Promise resolving true/false },
 *     on_leave(wizard) { ... اختياري: تُنفَّذ عند مغادرة الخطوة للأمام ... },
 *   }
 *
 * finish(wizard) في تعريف الويزارد نفسه تُنفَّذ بدل الانتقال لخطوة تالية
 * عند الضغط على زر الخطوة الأخيرة.
 */

frappe.provide("asset_mgmt_custom.Wizard");

asset_mgmt_custom.Wizard = class Wizard {
	constructor({ wrapper, title, subtitle, steps, finish, finish_label }) {
		this.wrapper = $(wrapper);
		this.title = title;
		this.subtitle = subtitle;
		this.steps = steps;
		this.finish = finish;
		this.finish_label = finish_label || __("إرسال");
		this.current = 0;
		this.state = {};
		this.controls = {};

		this.render_shell();
		this.render_step();
	}

	render_shell() {
		this.wrapper.empty();
		this.$root = $(`
			<div class="amc-wizard" dir="rtl">
				<div class="amc-wizard-header">
					<h3>${frappe.utils.escape_html(this.title)}</h3>
					${this.subtitle ? `<p class="text-muted">${frappe.utils.escape_html(this.subtitle)}</p>` : ""}
				</div>
				<div class="amc-wizard-progress"></div>
				<div class="amc-wizard-body"></div>
				<div class="amc-wizard-error alert alert-danger" style="display:none;"></div>
				<div class="amc-wizard-footer">
					<button class="btn btn-default amc-wizard-back">${__("رجوع")}</button>
					<div class="amc-wizard-footer-spacer"></div>
					<button class="btn btn-primary amc-wizard-next"></button>
				</div>
			</div>
		`).appendTo(this.wrapper);

		this.$progress = this.$root.find(".amc-wizard-progress");
		this.$body = this.$root.find(".amc-wizard-body");
		this.$error = this.$root.find(".amc-wizard-error");
		this.$back = this.$root.find(".amc-wizard-back");
		this.$next = this.$root.find(".amc-wizard-next");

		this.$back.on("click", () => this.go_back());
		this.$next.on("click", () => this.go_next());
	}

	render_progress() {
		this.$progress.empty();
		this.steps.forEach((step, i) => {
			const state = i < this.current ? "done" : (i === this.current ? "active" : "todo");
			$(`
				<div class="amc-wizard-step ${state}">
					<div class="amc-wizard-step-circle">${i < this.current ? "✓" : i + 1}</div>
					<div class="amc-wizard-step-label">${frappe.utils.escape_html(step.label)}</div>
				</div>
			`).appendTo(this.$progress);
		});
	}

	render_step() {
		this.clear_error();
		this.render_progress();
		this.$body.empty();
		const step = this.steps[this.current];
		step.render(this.$body, this);

		this.$back.toggle(this.current > 0);
		this.$next.text(this.current === this.steps.length - 1 ? this.finish_label : __("التالي"));
	}

	show_error(msg) {
		this.$error.text(msg).show();
	}

	clear_error() {
		this.$error.hide().text("");
	}

	async go_next() {
		const step = this.steps[this.current];
		this.clear_error();

		if (step.validate) {
			let ok;
			try {
				ok = await step.validate(this);
			} catch (e) {
				this.show_error(e.message || __("حدث خطأ. حاول مرة أخرى."));
				return;
			}
			if (!ok) return;
		}

		if (step.on_leave) {
			try {
				this.$next.prop("disabled", true);
				await step.on_leave(this);
			} catch (e) {
				this.show_error(e.message || __("حدث خطأ. حاول مرة أخرى."));
				this.$next.prop("disabled", false);
				return;
			}
			this.$next.prop("disabled", false);
		}

		if (this.current === this.steps.length - 1) {
			if (this.finish) {
				try {
					this.$next.prop("disabled", true);
					await this.finish(this);
				} catch (e) {
					this.show_error(e.message || __("حدث خطأ أثناء الإرسال. حاول مرة أخرى."));
				}
				this.$next.prop("disabled", false);
			}
			return;
		}

		this.current += 1;
		this.render_step();
	}

	go_back() {
		if (this.current === 0) return;
		this.clear_error();
		this.current -= 1;
		this.render_step();
	}

	/** أداة مساعدة: تُنشئ حقل Frappe قياسي (Link/Select/Data/Small Text...) داخل الخطوة الحالية. */
	make_field(parent, df, key) {
		const control = frappe.ui.form.make_control({
			parent: $(parent).get(0),
			df: df,
			render_input: true,
			only_input: false,
		});
		if (key) this.controls[key] = control;
		return control;
	}
};

/** رفع ملف (صورة) مرتبط بمستند موجود بالفعل — عبر REST مباشرة، بدون واجهة رفع منبثقة. */
asset_mgmt_custom.Wizard.upload_file = function (file, { doctype, docname, fieldname, is_private = 0 }) {
	const form_data = new FormData();
	form_data.append("file", file, file.name);
	form_data.append("doctype", doctype);
	form_data.append("docname", docname);
	form_data.append("fieldname", fieldname);
	form_data.append("is_private", is_private);

	return fetch("/api/method/upload_file", {
		method: "POST",
		headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
		body: form_data,
	}).then((res) => res.json());
};
