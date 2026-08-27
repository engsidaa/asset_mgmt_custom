frappe.query_reports["Department Asset Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
	],
};
