// Client Script – Asset Form
// يتحكم في حقول الحالة (جديد/مستعمل) ونسبة الإهلاك

frappe.ui.form.on("Asset", {
	refresh(frm) {
		_toggle_used_rate_field(frm);
		_set_sticker_code_highlight(frm);
	},

	custom_asset_condition(frm) {
		_toggle_used_rate_field(frm);

		// لو تغيرت الحالة لـ New، امسح نسبة الإهلاك الخاصة بالمستعمل
		if (frm.doc.custom_asset_condition === "New") {
			frm.set_value("custom_used_depreciation_rate", 0);
		}
	},

	custom_used_depreciation_rate(frm) {
		if (
			frm.doc.custom_asset_condition === "Used" &&
			frm.doc.custom_used_depreciation_rate > 0
		) {
			frappe.show_alert(
				{
					message: __(
						"Used asset depreciation rate {0}% will be applied to all finance books on save.",
						[frm.doc.custom_used_depreciation_rate]
					),
					indicator: "blue",
				},
				5
			);
		}
	},
});

function _toggle_used_rate_field(frm) {
	const is_used = frm.doc.custom_asset_condition === "Used";
	frm.toggle_reqd("custom_used_depreciation_rate", is_used);
	frm.toggle_display("custom_used_depreciation_rate", is_used);
}

function _set_sticker_code_highlight(frm) {
	if (!frm.doc.custom_sticker_code) {
		frm.set_intro(
			__("Sticker code not assigned yet. Please update after placing the physical sticker on the asset."),
			"yellow"
		);
	}
}
