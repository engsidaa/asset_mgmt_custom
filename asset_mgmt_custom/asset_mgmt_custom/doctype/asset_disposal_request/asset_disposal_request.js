frappe.ui.form.on("Asset Disposal Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Pending Approval") {
			if (frappe.user.has_role(["Asset Manager", "System Manager"])) {
				frm.add_custom_button(__("Approve"), () => {
					frappe.confirm(
						__("Approve this disposal request for {0}?", [frm.doc.asset_name || frm.doc.asset]),
						() => frm.call("approve").then(() => frm.reload_doc())
					);
				}, __("Actions")).addClass("btn-success");

				frm.add_custom_button(__("Reject"), () => {
					const d = new frappe.ui.Dialog({
						title: __("Reject Disposal Request"),
						fields: [{ fieldname: "reason", label: __("Rejection Reason"), fieldtype: "Small Text", reqd: 1 }],
						primary_action_label: __("Reject"),
						primary_action(vals) {
							frm.call("reject", { reason: vals.reason }).then(() => {
								d.hide();
								frm.reload_doc();
							});
						},
					});
					d.show();
				}, __("Actions")).addClass("btn-danger");
			}
		}
	},

	asset(frm) {
		if (frm.doc.asset) {
			frappe.db.get_value("Asset", frm.doc.asset, "value_after_depreciation", (r) => {
				frm.set_value("book_value", r.value_after_depreciation || 0);
			});
		}
	},
});
