frappe.query_reports["Depreciation Forecast"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "forecast_years", label: __("Forecast Years"), fieldtype: "Select", options: "1\n2\n3\n5", default: "3" },
	],
};
