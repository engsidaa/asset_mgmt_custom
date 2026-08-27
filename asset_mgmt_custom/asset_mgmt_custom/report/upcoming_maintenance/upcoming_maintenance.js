frappe.query_reports["Upcoming Maintenance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "days", label: __("Due in Next (Days)"), fieldtype: "Select", options: "30\n60\n90", default: "30" },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
	],
	formatter(value, row, column, data, default_formatter) {
		let v = default_formatter(value, row, column, data);
		if (column.fieldname === "days_until_due" && data) {
			const d = parseInt(data.days_until_due || 0);
			const color = d < 0 ? "#ef4444" : d <= 7 ? "#f59e0b" : "#10b981";
			v = `<span style="color:${color};font-weight:600;">${value}</span>`;
		}
		return v;
	},
};
