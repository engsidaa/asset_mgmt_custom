frappe.query_reports["Asset Age Analysis"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
	],
	formatter(value, row, column, data, default_formatter) {
		let v = default_formatter(value, row, column, data);
		if (column.fieldname === "age_bracket" && data) {
			const colors = { "5+ Years": "#fde68a", "3 – 5 Years": "#d1fae5", "1 – 3 Years": "#dbeafe", "< 1 Year": "#e0e7ff" };
			const bg = colors[data.age_bracket];
			if (bg) v = `<span style="background:${bg};padding:2px 8px;border-radius:4px;font-size:12px;">${value}</span>`;
		}
		return v;
	},
};
