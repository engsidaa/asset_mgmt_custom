frappe.views.calendar["Asset Work Order"] = {
	fields: ["request_date", "completion_date", "status", "title", "priority", "branch", "work_type", "name"],
	field_map: {
		start: "request_date",
		end: "completion_date",
		id: "name",
		title: "title",
		status: "status",
	},
	filters: [
		{
			fieldtype: "Link",
			fieldname: "branch",
			options: "Branch",
			label: __("الفرع"),
		},
		{
			fieldtype: "Select",
			fieldname: "work_type",
			options: "صيانة وقائية\nإصلاح\nفحص\nطارئ\nتحسين",
			label: __("نوع العمل"),
		},
	],
	get_css_class: function (data) {
		if (data.status === "مكتمل") {
			return "success";
		} else if (data.status === "قيد التنفيذ") {
			return "warning";
		} else if (data.status === "ملغي" || data.status === "مرفوض") {
			return "danger";
		} else {
			return "default";
		}
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
