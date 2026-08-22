// Client Script – Asset Repair Form
// يحسب إجمالي التكلفة شاملاً أجر العمالة

frappe.ui.form.on("Asset Repair", {
	refresh(frm) {
		_update_total_with_labor(frm);
	},

	custom_labor_cost(frm) {
		_update_total_with_labor(frm);
	},

	repair_cost(frm) {
		_update_total_with_labor(frm);
	},
});

function _update_total_with_labor(frm) {
	const labor = flt(frm.doc.custom_labor_cost);
	const repair = flt(frm.doc.repair_cost);

	if (labor > 0) {
		const total = repair + labor;
		frm.set_intro(
			__("Total Repair Cost (including labor): {0}", [
				format_currency(total, frappe.defaults.get_default("currency")),
			]),
			"blue"
		);
	}
}
