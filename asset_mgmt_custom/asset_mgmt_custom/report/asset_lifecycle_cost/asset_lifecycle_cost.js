frappe.query_reports["Asset Lifecycle Cost"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "from_date", label: __("Purchase From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Purchase To"), fieldtype: "Date" },
	],
	formatter(value, row, column, data, default_formatter) {
		let v = default_formatter(value, row, column, data);
		if (column.fieldname === "cost_ratio_pct" && data) {
			const pct = parseFloat(data.cost_ratio_pct || 0);
			const color = pct >= 150 ? "#ef4444" : pct >= 120 ? "#f59e0b" : "#10b981";
			v = `<span style="color:${color};font-weight:600;">${value}</span>`;
		}
		return v;
	},
};
