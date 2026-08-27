frappe.query_reports["Asset Insurance Summary"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nActive\nExpiring Soon\nExpired\nNo Insurance" },
    ],
};
