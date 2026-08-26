frappe.query_reports["Warranty Expiry Alerts"] = {
	filters: [
		{
			fieldname: "days",
			label: __("Expiring Within (Days)"),
			fieldtype: "Select",
			options: "30\n60\n90",
			default: "30",
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Location",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_remaining" && data) {
			if (data.days_remaining <= 14) {
				value = `<span style="color:var(--red-600);font-weight:600;">${value}</span>`;
			} else if (data.days_remaining <= 30) {
				value = `<span style="color:var(--orange-500);font-weight:600;">${value}</span>`;
			}
		}
		return value;
	},
};
