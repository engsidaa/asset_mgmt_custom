frappe.query_reports["Asset Energy Cost by Branch"] = {
    filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "from_month", label: __("From Month (YYYY-MM)"), fieldtype: "Data" },
        { fieldname: "to_month", label: __("To Month (YYYY-MM)"), fieldtype: "Data" },
    ],
};
