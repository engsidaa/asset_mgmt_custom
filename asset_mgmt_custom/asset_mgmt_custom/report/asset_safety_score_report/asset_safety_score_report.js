frappe.query_reports["Asset Safety Score Report"] = {
    filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "overall_result", label: __("Result"), fieldtype: "Select", options: "\nPass\nFail\nNeeds Action" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
    ],
};
