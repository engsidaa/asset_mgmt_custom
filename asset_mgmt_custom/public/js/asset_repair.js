// Client Script – Asset Repair Form
// يتحكم في:
//   1. حساب إجمالي التكلفة شاملاً العمالة وعرضه
//   2. تحذير عند اكتمال الإصلاح لرفع الصور
//   3. عرض مدة التوقف (Downtime)

frappe.ui.form.on("Asset Repair", {

	// -----------------------------------------------------------------------
	// Refresh
	// -----------------------------------------------------------------------
	refresh(frm) {
		_update_cost_display(frm);
		_toggle_completion_warnings(frm);
	},

	// -----------------------------------------------------------------------
	// تغييرات التكلفة
	// -----------------------------------------------------------------------
	custom_labor_cost(frm) { _update_cost_display(frm); },
	repair_cost(frm)       { _update_cost_display(frm); },

	// -----------------------------------------------------------------------
	// حالة الإصلاح
	// -----------------------------------------------------------------------
	repair_status(frm) {
		_toggle_completion_warnings(frm);

		if (frm.doc.repair_status === "Completed") {
			frappe.show_alert({
				message: __(
					"Please fill in Technician Name, Repair Notes, and upload Before/After images before saving."
				),
				indicator: "orange",
			}, 8);

			// اقتراح تاريخ الاكتمال تلقائياً لو فاضي
			if (!frm.doc.completion_date) {
				frm.set_value("completion_date", frappe.datetime.now_datetime());
			}
		}
	},
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _update_cost_display(frm) {
	const labor  = flt(frm.doc.custom_labor_cost);
	const repair = flt(frm.doc.repair_cost);

	// إجمالي تكلفة العناصر من المخزن
	let stock_total = 0;
	(frm.doc.stock_items || []).forEach(row => { stock_total += flt(row.total_value); });

	const grand_total = repair + labor + stock_total;
	const currency    = frappe.defaults.get_default("currency") || "";

	if (grand_total > 0) {
		const parts = [];
		if (repair > 0)      parts.push(__("External repair: {0}", [format_currency(repair, currency)]));
		if (labor > 0)       parts.push(__("Labor: {0}", [format_currency(labor, currency)]));
		if (stock_total > 0) parts.push(__("Stock items: {0}", [format_currency(stock_total, currency)]));
		parts.push(`<b>${__("Grand Total: {0}", [format_currency(grand_total, currency)])}</b>`);

		frm.set_intro(parts.join(" &nbsp;|&nbsp; "), "blue");
	} else {
		frm.set_intro("", false);
	}
}

function _toggle_completion_warnings(frm) {
	const is_completed = frm.doc.repair_status === "Completed";

	frm.toggle_reqd("custom_technician_name", is_completed);
	frm.toggle_reqd("custom_repair_notes",    is_completed);
	frm.toggle_reqd("completion_date",        is_completed);

	// تمييز بصري لحقل الصور عند الاكتمال
	frm.set_df_property(
		"custom_after_repair_image",
		"description",
		is_completed
			? __("⚠️ Required: Upload a photo showing the completed repair.")
			: __("Photo of the asset after repair.")
	);
}
