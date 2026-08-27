frappe.query_reports["Branch Asset Handover"] = {
	filters: [
		{
			fieldname: "cost_center",
			label: __("Branch / Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			reqd: 1,
		},
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "outgoing_manager",
			label: __("Outgoing Manager"),
			fieldtype: "Data",
		},
		{
			fieldname: "incoming_manager",
			label: __("Incoming Manager"),
			fieldtype: "Data",
		},
	],
};
