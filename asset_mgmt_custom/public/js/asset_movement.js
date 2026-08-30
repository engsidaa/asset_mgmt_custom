// Client Script – Asset Movement Form
// يتحكم في:
//   1. التحقق من Tag (Sticker/Iron Code) قبل النقل بين الفروع (Transfer)
//   2. عرض مركز التكلفة للموقع الهدف
//   3. إشعار عند استلام أصل احتياطي
//   4. عرض تفاصيل السائق والسيارة عند Transfer
//   5. شارة "In Transit" في رأس النموذج

frappe.ui.form.on("Asset Movement", {

	// -----------------------------------------------------------------------
	// Refresh
	// -----------------------------------------------------------------------
	refresh(frm) {
		_render_movement_summary(frm);
		_show_transit_badge(frm);

		// Confirm Receipt button for submitted Transfer movements not yet confirmed
		if (frm.doc.docstatus === 1 && frm.doc.purpose === "Transfer" && !frm.doc.custom_receipt_confirmed) {
			frm.add_custom_button(__("Confirm Receipt (تأكيد الاستلام)"), function () {
				frappe.confirm(
					__("Confirm that all assets in this movement have been physically received?"),
					function () {
						frappe.call({
							method: "asset_mgmt_custom.overrides.asset_movement.confirm_receipt",
							args: { movement_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Confirming receipt…"),
							callback(r) {
								if (r.message && r.message.length) {
									frappe.show_alert({
										message: __("{0} asset(s) confirmed as received", [r.message.length]),
										indicator: "green"
									});
									frm.reload_doc();
								}
							}
						});
					}
				);
			}, __("Actions")).addClass("btn-success");
		}
	},

	// -----------------------------------------------------------------------
	// نوع الحركة
	// -----------------------------------------------------------------------
	purpose(frm) {
		_render_movement_summary(frm);
		_toggle_transit_section(frm);
	},

	// -----------------------------------------------------------------------
	// اختيار سائق من سجل السائقين — يملأ اسمه تلقائياً (اختياري)
	// -----------------------------------------------------------------------
	custom_driver(frm) {
		if (!frm.doc.custom_driver) return;
		frappe.db.get_value("Driver", frm.doc.custom_driver, "full_name").then(({ message }) => {
			if (message && message.full_name) {
				frm.set_value("custom_driver_name", message.full_name);
			}
		});
	},
});

frappe.ui.form.on("Asset Movement Item", {

	// -----------------------------------------------------------------------
	// عند اختيار أصل في الجدول
	// -----------------------------------------------------------------------
	asset(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.asset) return;

		if (frm.doc.purpose === "Transfer") {
			frappe.db.get_value("Asset", row.asset, [
				"custom_sticker_code", "custom_is_spare", "asset_name",
				"custom_tag_type", "custom_iron_code", "custom_operational_status"
			]).then(({ message }) => {
				const tag_type = message.custom_tag_type;
				const sticker  = message.custom_sticker_code;
				const iron     = message.custom_iron_code;
				const op_status = message.custom_operational_status;

				if (op_status === "Incomplete") {
					frappe.show_alert({
						message: __(
							"Asset <b>{0}</b> is Incomplete. Activate it before transferring.",
							[message.asset_name || row.asset]
						),
						indicator: "red",
					}, 8);
				} else if (tag_type === "Iron Code" && !iron) {
					frappe.show_alert({
						message: __(
							"Asset <b>{0}</b> has no Iron Code. Assign before transfer.",
							[message.asset_name || row.asset]
						),
						indicator: "red",
					}, 8);
				} else if (!tag_type && !sticker) {
					frappe.show_alert({
						message: __(
							"Asset <b>{0}</b> has no tag (Sticker Code or Iron Code). Assign before transfer.",
							[message.asset_name || row.asset]
						),
						indicator: "red",
					}, 8);
				}

				if (message.custom_is_spare) {
					frappe.show_alert({
						message: __(
							"Asset <b>{0}</b> is a Spare asset. Upon receipt it will be automatically activated.",
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
							"Location <b>{0}</b> has no Cost Center configured. Depreciation cost center will not be updated.",
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
		msg  += " &nbsp;|&nbsp; " + __("Tag (Sticker/Iron Code) required for each asset.");
	} else if (purpose === "Receipt") {
		color = "green";
		msg  += " &nbsp;|&nbsp; " + __("Spare assets will be activated automatically upon submission.");
	}

	frm.dashboard.add_comment(msg, color, true);
}

function _show_transit_badge(frm) {
	// كانت بتظهر الشارة طول ما docstatus=1 وpurpose=Transfer، حتى بعد
	// تأكيد الاستلام فعلاً (custom_receipt_confirmed=1) — يعني السند بيفضل
	// شايل شارة "In Transit" للأبد حتى لو الأصل وصل ورجع Operational بالفعل.
	if (frm.doc.docstatus !== 1 || frm.doc.purpose !== "Transfer" || frm.doc.custom_receipt_confirmed) return;

	const in_transit = (frm.doc.assets || []).some(function(row) {
		return row.asset;
	});

	if (in_transit) {
		frm.dashboard.set_headline(
			`<span class="indicator-pill orange">${__("In Transit")}</span>`
		);
	}
}

function _toggle_transit_section(frm) {
	const show = frm.doc.purpose === "Transfer";
	frm.toggle_display("custom_transit_section", show);
	frm.toggle_display("custom_driver", show);
	frm.toggle_display("custom_driver_name", show);
	frm.toggle_display("custom_transit_col", show);
	frm.toggle_display("custom_vehicle_number", show);
	frm.toggle_display("custom_expected_arrival", show);
}
