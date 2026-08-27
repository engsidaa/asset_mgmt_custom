frappe.query_reports["Maintenance Cost Ratio"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "threshold_percent", label: __("Flag Threshold (%)"), fieldtype: "Float", default: 30, description: "Flag assets where repair cost exceeds this % of current value" },
	],
	formatter(value, row, column, data, default_formatter) {
		let v = default_formatter(value, row, column, data);
		if (column.fieldname === "flag" && data && data.flag) {
			const color = data.flag.startsWith("⚠") ? "#ef4444" : "#f59e0b";
			v = `<span style="color:${color};font-weight:600;">${value}</span>`;
		}
		if (column.fieldname === "repair_ratio_pct" && data) {
			const pct = parseFloat(data.repair_ratio_pct || 0);
			const color = pct >= 30 ? "#ef4444" : pct >= 20 ? "#f59e0b" : "#10b981";
			v = `<span style="color:${color};font-weight:600;">${value}</span>`;
		}
		return v;
	},
};
