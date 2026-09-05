const FINAL_STATUSES = ["مكتمل", "ملغي", "مرفوض"];
const MAINTENANCE_ROLES = ["Asset Technician", "Asset Manager", "System Manager"];

frappe.ui.form.on("Asset Work Order", {
	refresh(frm) {
		const is_open = frm.doc.docstatus === 1 && !FINAL_STATUSES.includes(frm.doc.status);
		const is_maintenance_staff = MAINTENANCE_ROLES.some((r) => frappe.user_roles.includes(r));

		if (is_open && is_maintenance_staff) {
			frm.add_custom_button(__("إتمام أمر العمل"), () => {
				frappe.confirm(
					__("سيتم تحديد الحالة كـ 'مكتمل' وترحيل تكلفته الفعلية محاسبياً (إن وُجدت). متابعة؟"),
					() => {
						frappe.call({
							method: "complete_work_order",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("جارٍ إتمام أمر العمل..."),
							callback(r) {
								if (r.message) frm.reload_doc();
							},
						});
					}
				);
			}, __("الحالة"));

			frm.add_custom_button(__("رفض الطلب"), () => {
				frappe.prompt(
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("سبب الرفض"),
						reqd: 1,
					},
					(values) => {
						frappe.call({
							method: "reject_work_order",
							doc: frm.doc,
							args: { reason: values.reason },
							freeze: true,
							freeze_message: __("جارٍ رفض الطلب..."),
							callback(r) {
								if (r.message) frm.reload_doc();
							},
						});
					},
					__("رفض طلب الصيانة"),
					__("رفض")
				);
			}, __("الحالة"));
		}

		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("عرض قيد اليومية"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
			}, __("المحاسبة"));
		}
	},
});
