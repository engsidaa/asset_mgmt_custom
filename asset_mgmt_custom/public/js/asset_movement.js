// Client Script – Asset Movement Form
// يتحكم في:
//   1. التحقق من كود الستيكر قبل النقل بين الفروع (Transfer)
//   2. عرض مركز التكلفة للموقع الهدف
//   3. إشعار عند استلام أصل احتياطي

frappe.ui.form.on("Asset Movement", {

	// -----------------------------------------------------------------------
	// Refresh
	// -----------------------------------------------------------------------
	refresh(frm) {
		_render_movement_summary(frm);
	},

	// -----------------------------------------------------------------------
	// نوع الحركة
	// -----------------------------------------------------------------------
	purpose(frm) {
		_render_movement_summary(frm);
	},
});

frappe.ui.form.on("Asset Movement Item", {

	// -----------------------------------------------------------------------
	// عند اختيار أصل في الجدول
	// -----------------------------------------------------------------------
	asset(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.asset) return;

		// التحقق من كود الستيكر لو كانت الحركة "Transfer"
		if (frm.doc.purpose === "Transfer") {
			frappe.db.get_value("Asset", row.asset, ["custom_sticker_code", "custom_is_spare", "asset_name"])
				.then(({ message }) => {
					if (!message.custom_sticker_code) {
						frappe.show_alert({
							message: __(
								"⚠️ Asset <b>{0}</b> has no Sticker Code. You must assign one before transferring.",
								[message.asset_name || row.asset]
							),
							indicator: "red",
						}, 8);
					}

					if (message.custom_is_spare) {
						frappe.show_alert({
							message: __(
								"ℹ️ Asset <b>{0}</b> is a Spare asset. Upon receipt it will be automatically activated.",
								[message.asset_name || row.asset]
							),
							indicator: "blue",
						}, 6);
					}
				});
		}
	},

	// -----------------------------------------------------------------------
	// عند اختيار الموقع الهدف
	// -----------------------------------------------------------------------
	target_location(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.target_location) return;

		frappe.db.get_value("Location", row.target_location, "custom_cost_center")
			.then(({ message }) => {
				if (message && message.custom_cost_center) {
					frappe.show_alert({
						message: __(
							"Cost center <b>{0}</b> will be applied to asset depreciation after transfer to <b>{1}</b>.",
							[message.custom_cost_center, row.target_location]
						),
						indicator: "blue",
					}, 6);
				} else {
					frappe.show_alert({
						message: __(
							"⚠️ Location <b>{0}</b> has no Cost Center configured. Depreciation cost center will not be updated.",
							[row.target_location]
						),
						indicator: "orange",
					}, 6);
				}
			});
	},
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _render_movement_summary(frm) {
	if (frm.is_new()) return;

	const purpose = frm.doc.purpose;
	const asset_count = (frm.doc.assets || []).length;

	if (!purpose || !asset_count) return;

	let color = "blue";
	let msg   = __("{0} asset(s) – Purpose: {1}", [asset_count, purpose]);

	if (purpose === "Transfer") {
		color = "orange";
		msg  += " &nbsp;|&nbsp; " + __("Sticker Code required for each asset.");
	} else if (purpose === "Receipt") {
		color = "green";
		msg  += " &nbsp;|&nbsp; " + __("Spare assets will be activated automatically upon submission.");
	}

	frm.dashboard.add_comment(msg, color, true);
}
