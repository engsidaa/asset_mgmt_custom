// Client Script – Asset Form
// يتحكم في:
//   1. حالة الأصل (New/Used) ونسبة إهلاك المستعمل
//   2. علامة الأصل الاحتياطي (Spare)
//   3. تحذير كود الستيكر
//   4. ملخص تكلفة الصيانة

frappe.ui.form.on("Asset", {

	// -----------------------------------------------------------------------
	// Refresh – يُعيد بناء الـ UI عند كل تحميل
	// -----------------------------------------------------------------------
	refresh(frm) {
		_toggle_used_rate_field(frm);
		_render_condition_badge(frm);
		_show_sticker_code_alert(frm);
		_show_maintenance_summary(frm);
	},

	// -----------------------------------------------------------------------
	// حالة الأصل
	// -----------------------------------------------------------------------
	custom_asset_condition(frm) {
		_toggle_used_rate_field(frm);
		_render_condition_badge(frm);

		if (frm.doc.custom_asset_condition === "New") {
			frm.set_value("custom_used_depreciation_rate", 0);
			frappe.show_alert({ message: __("Standard depreciation rate from Asset Category will be used."), indicator: "green" }, 4);
		} else if (frm.doc.custom_asset_condition === "Used") {
			frappe.show_alert({ message: __("Please set the Used Asset Depreciation Rate (%) below."), indicator: "orange" }, 5);
		}
	},

	custom_used_depreciation_rate(frm) {
		const rate = frm.doc.custom_used_depreciation_rate;
		if (frm.doc.custom_asset_condition === "Used" && rate > 0) {
			frappe.show_alert({
				message: __("Rate {0}% will be applied to all finance books on save.", [rate]),
				indicator: "blue",
			}, 5);
		}
	},

	// -----------------------------------------------------------------------
	// الأصل الاحتياطي
	// -----------------------------------------------------------------------
	custom_is_spare(frm) {
		_render_condition_badge(frm);
		if (frm.doc.custom_is_spare) {
			frm.set_value("calculate_depreciation", 0);
			frappe.show_alert({
				message: __("Spare asset – depreciation disabled until activated via Asset Receipt."),
				indicator: "orange",
			}, 7);
		}
	},

	// -----------------------------------------------------------------------
	// كود الستيكر
	// -----------------------------------------------------------------------
	custom_sticker_code(frm) {
		_show_sticker_code_alert(frm);
	},
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _toggle_used_rate_field(frm) {
	const is_used = frm.doc.custom_asset_condition === "Used";
	frm.toggle_display("custom_used_depreciation_rate", is_used);
	frm.toggle_reqd("custom_used_depreciation_rate", is_used && !!frm.doc.calculate_depreciation);
}

function _render_condition_badge(frm) {
	frm.dashboard.clear_headline();
	const condition = frm.doc.custom_asset_condition;
	const is_spare  = frm.doc.custom_is_spare;
	if (!condition && !is_spare) return;

	const badges = [];
	if (condition === "New")  badges.push(`<span class="indicator-pill green">${__("New Asset")}</span>`);
	if (condition === "Used") badges.push(`<span class="indicator-pill orange">${__("Used Asset")}</span>`);
	if (is_spare)             badges.push(`<span class="indicator-pill blue">${__("Spare / احتياطي")}</span>`);

	if (badges.length) frm.dashboard.set_headline(badges.join("&nbsp;"));
}

function _show_sticker_code_alert(frm) {
	if (frm.is_new()) return;
	if (!frm.doc.custom_sticker_code) {
		frm.set_intro(
			__("<b>Sticker Code not assigned yet.</b> Update this field after placing the physical sticker on the asset."),
			"yellow"
		);
	} else {
		frm.set_intro("", false);
	}
}

function _show_maintenance_summary(frm) {
	if (frm.is_new()) return;
	const total     = frm.doc.custom_total_maintenance_cost;
	const last_date = frm.doc.custom_last_maintenance_date;
	if (!total && !last_date) return;

	frm.dashboard.add_comment(
		__(
			"Total maintenance cost: <b>{0}</b> | Last maintenance: <b>{1}</b>",
			[
				format_currency(total || 0, frappe.defaults.get_default("currency") || ""),
				last_date ? frappe.datetime.str_to_user(last_date) : __("N/A"),
			]
		),
		"blue",
		true
	);
}
