frappe.query_reports["Maintenance Cost Detail"] = {
	filters: [
		{ fieldname: "asset", label: __("Asset"), fieldtype: "Link", options: "Asset" },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
