frappe.query_reports["Asset Incident Summary"] = {
    filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "severity", label: __("Severity"), fieldtype: "Select", options: "\nLow\nMedium\nHigh\nCritical" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nUnder Investigation\nResolved\nClosed" },
    ],
};
