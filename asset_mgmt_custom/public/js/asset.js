// Client Script – Asset Form
// يتحكم في:
//   1. حالة الأصل (New/Used) ونسبة إهلاك المستعمل
//   2. علامة الأصل الاحتياطي (Spare)
//   3. تحذير كود الستيكر / Tag
//   4. ملخص تكلفة الصيانة
//   5. زر "وضع علامة مُرمَّز" ثم زر "Set Operational" — خطوتان منفصلتان

frappe.ui.form.on("Asset", {

	// -----------------------------------------------------------------------
	// Refresh – يُعيد بناء الـ UI عند كل تحميل
	// -----------------------------------------------------------------------
	refresh(frm) {
		_toggle_used_rate_field(frm);
		_render_condition_badge(frm);
		_show_sticker_alert(frm);
		_render_maintenance_summary(frm);
		_add_mark_coded_button(frm);
		_add_set_operational_button(frm);
		_add_print_tag_button(frm);
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
		_show_sticker_alert(frm);
	},

	custom_tag_type(frm) {
		_show_sticker_alert(frm);
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
	const status    = frm.doc.custom_operational_status;
	const coding    = frm.doc.custom_coding_status;

	const badges = [];
	if (condition === "New")  badges.push(`<span class="indicator-pill green">${__("New Asset")}</span>`);
	if (condition === "Used") badges.push(`<span class="indicator-pill orange">${__("Used Asset")}</span>`);
	if (is_spare)             badges.push(`<span class="indicator-pill blue">${__("Spare / احتياطي")}</span>`);

	if (coding) {
		badges.push(`<span class="indicator-pill ${coding === "Coded" ? "green" : "red"}">${__(coding)}</span>`);
	}

	const statusColors = { Operational: "green", Incomplete: "red", "In Transit": "orange" };
	if (status) {
		const color = statusColors[status] || "gray";
		badges.push(`<span class="indicator-pill ${color}">${__(status)}</span>`);
	}

	if (badges.length) frm.dashboard.set_headline(badges.join("&nbsp;"));
}

function _show_sticker_alert(frm) {
	if (frm.is_new()) return;
	const tag_type = frm.doc.custom_tag_type;
	const sticker  = frm.doc.custom_sticker_code;
	const iron     = frm.doc.custom_iron_code;

	if (tag_type === "Iron Code" && !iron) {
		frm.dashboard.add_comment(__("Iron Code is missing. Please enter it before activating."), "orange");
	} else if (!tag_type && !sticker) {
		frm.dashboard.add_comment(__("No tag assigned. Assign a Sticker Code or Iron Code."), "orange");
	} else {
		frm.set_intro("", false);
	}
}

function _render_maintenance_summary(frm) {
	if (frm.is_new()) return;
	const cost = frm.doc.custom_total_maintenance_cost;
	const date = frm.doc.custom_last_maintenance_date;
	if (!cost && !date) return;

	frm.dashboard.add_comment(
		__(
			"Total maintenance cost: <b>{0}</b> | Last maintenance: <b>{1}</b>",
			[
				format_currency(cost || 0, frappe.defaults.get_default("currency") || ""),
				date ? frappe.datetime.str_to_user(date) : __("N/A"),
			]
		),
		"blue",
		true
	);
}

function _add_mark_coded_button(frm) {
	if (frm.doc.docstatus !== 1) return;
	if (frm.doc.custom_coding_status === "Coded") return;

	frm.add_custom_button(__("Mark Coded (وضع علامة مُرمَّز)"), function () {
		frappe.confirm(
			__("Mark asset <b>{0}</b> as Coded? Requires tag code + before/after photos to already be attached.", [frm.doc.asset_name]),
			function () {
				frappe.call({
					method: "asset_mgmt_custom.overrides.asset.mark_coded",
					args: { asset_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Marking asset as Coded…"),
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Asset is now Coded"), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			}
		);
	}, __("Actions")).addClass("btn-primary");
}

function _add_set_operational_button(frm) {
	if (frm.doc.docstatus !== 1) return;
	if (frm.doc.custom_operational_status === "Operational") return;
	if (frm.doc.custom_coding_status !== "Coded") return; // must be coded first

	frm.add_custom_button(__("Set Operational (تعيين كتشغيلي)"), function () {
		frappe.confirm(
			__("Set asset <b>{0}</b> to Operational? Depreciation will start from today.", [frm.doc.asset_name]),
			function () {
				frappe.call({
					method: "asset_mgmt_custom.overrides.asset.set_operational",
					args: { asset_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Setting asset to Operational…"),
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Asset is now Operational"), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			}
		);
	}, __("Actions")).addClass("btn-primary");
}

function _add_print_tag_button(frm) {
	if (frm.doc.__islocal) return;
	frm.add_custom_button(__("Print Asset Tag"), function () {
		frappe.utils.print(frm.doctype, frm.docname, "Asset Tag");
	}, __("Print"));
}
