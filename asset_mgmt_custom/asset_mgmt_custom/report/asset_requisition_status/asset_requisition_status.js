frappe.query_reports["Asset Requisition Status"] = {
	filters: [
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: "\nDraft\nPending Approval\nApproved\nRejected\nFulfilled" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
	],
};
