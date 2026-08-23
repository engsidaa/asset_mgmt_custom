// Client Script – Asset Requisition Form

frappe.ui.form.on("Asset Requisition", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && frm.doc.spare_available) {
			frm.add_custom_button(__("Create Asset Movement"), function () {
				frappe.call({
					method: "create_asset_movement",
					doc: frm.doc,
					callback(r) {
						if (r.message) {
							frappe.set_route("Form", "Asset Movement", r.message);
						}
					},
				});
			}, __("Actions"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.spare_available) {
			frm.add_custom_button(__("Create Purchase Request"), function () {
				frappe.call({
					method: "create_purchase_requisition",
					doc: frm.doc,
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: __("Material Request created: {0}", [r.message]), indicator: "green" });
							frappe.set_route("Form", "Material Request", r.message);
						}
					}
				});
			}, __("Actions"));
		}

		if (frm.doc.spare_available) {
			frm.dashboard.add_comment(
				__("Spare asset available: {0}", [frm.doc.spare_asset]),
				"green"
			);
		} else if (frm.doc.docstatus === 0) {
			frm.dashboard.add_comment(
				__("No spare asset found for this category. A purchase requisition may be needed."),
				"orange"
			);
		}
	},

	asset_category(frm) {
		if (frm.doc.asset_category) {
			frm.save();
		}
	},
});
