frappe.ui.form.on("Asset Physical Audit", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Assets from Branch"), () => {
				if (!frm.doc.cost_center) {
					frappe.msgprint(__("Please set a Branch / Cost Center first."));
					return;
				}
				frappe.confirm(
					__("This will replace the current items list with all assets in {0}. Continue?", [frm.doc.cost_center]),
					() => {
						frm.call("fetch_assets").then(r => {
							if (r.message !== undefined) {
								frappe.show_alert({
									message: __("{0} assets loaded from {1}", [r.message, frm.doc.cost_center]),
									indicator: "green",
								});
								frm.refresh_field("items");
								frm.refresh_field("total_assets");
							}
						});
					}
				);
			}, __("Actions"));
		}

		// Progress bar
		if (frm.doc.total_assets) {
			const done = (frm.doc.found_count || 0) + (frm.doc.missing_count || 0) + (frm.doc.damaged_count || 0);
			frm.dashboard.add_progress(
				__("Verification Progress"),
				Math.round((done / frm.doc.total_assets) * 100)
			);
		}
	},
});
