frappe.query_reports["Asset Checkout Status"] = {
    filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nChecked Out\nOverdue\nReturned" },
    ],
};
