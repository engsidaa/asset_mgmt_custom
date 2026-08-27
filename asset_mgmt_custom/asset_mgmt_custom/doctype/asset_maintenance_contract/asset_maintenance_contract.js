frappe.ui.form.on("Asset Maintenance Contract", {
	refresh(frm) {
		if (frm.doc.end_date && frappe.datetime.get_diff(frm.doc.end_date, frappe.datetime.get_today()) < 0) {
			frm.dashboard.set_headline_alert(
				__("This contract has expired."),
				"red"
			);
		} else if (frm.doc.end_date && frappe.datetime.get_diff(frm.doc.end_date, frappe.datetime.get_today()) <= 30) {
			frm.dashboard.set_headline_alert(
				__("Contract expires in {0} days.", [frappe.datetime.get_diff(frm.doc.end_date, frappe.datetime.get_today())]),
				"orange"
			);
		}
	},
});
