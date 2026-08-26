frappe.query_reports["CapEx Capitalization"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "asset",
			label: __("Asset"),
			fieldtype: "Link",
			options: "Asset",
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "excess" && data && data.excess > 0) {
			value = `<span style="color:var(--blue-600);font-weight:600;">${value}</span>`;
		}
		return value;
	},
};
