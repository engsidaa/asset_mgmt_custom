frappe.ui.form.on("Asset Loan", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Active") {
			frm.add_custom_button(__("Record Return"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Record Asset Return"),
					fields: [
						{ fieldname: "actual_return_date", label: __("Return Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
						{ fieldname: "return_condition", label: __("Return Condition"), fieldtype: "Select", options: ["Good", "Damaged", "Lost"], reqd: 1 },
					],
					primary_action_label: __("Confirm Return"),
					primary_action(vals) {
						frappe.call({
							method: "frappe.client.set_value",
							args: {
								doctype: "Asset Loan",
								name: frm.doc.name,
								fieldname: {
									actual_return_date: vals.actual_return_date,
									return_condition: vals.return_condition,
									status: "Returned",
								},
							},
							callback() {
								d.hide();
								frm.reload_doc();
							},
						});
					},
				});
				d.show();
			}, __("Actions"));
		}
	},
});
