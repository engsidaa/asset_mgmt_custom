frappe.query_reports["Asset Spare Parts Status"] = {
    filters: [
        { fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
        { fieldname: "stock_status", label: __("Stock Status"), fieldtype: "Select", options: "\nAll\nOK\nLow\nCritical", default: "All" },
    ],
};
