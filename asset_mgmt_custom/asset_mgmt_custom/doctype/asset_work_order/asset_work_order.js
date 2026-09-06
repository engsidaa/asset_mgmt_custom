const FINAL_STATUSES = ["مكتمل", "ملغي", "مرفوض"];
const UNRESTRICTED_MAINTENANCE_ROLES = ["Asset Technician", "Asset Manager", "System Manager"];

frappe.ui.form.on("Asset Work Order", {
	refresh(frm) {
		const is_open = frm.doc.docstatus === 1 && !FINAL_STATUSES.includes(frm.doc.status);
		const is_unrestricted_staff = UNRESTRICTED_MAINTENANCE_ROLES.some((r) => frappe.user_roles.includes(r));
		// مورد صيانة خارجي (Maintenance Vendor) يقدر يتصرف بس في الأمر
		// المُسنَد له هو تحديداً — نفس القيد المفروض على السيرفر
		// (has_permission/get_permission_query_conditions).
		const is_assigned_vendor = frappe.user_roles.includes("Maintenance Vendor")
			&& frm.doc.assigned_technician === frappe.session.user;
		const is_maintenance_staff = is_unrestricted_staff || is_assigned_vendor;

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

		if (frm.doc.asset_repair) {
			frm.add_custom_button(__("عرض سجل الإصلاح المُرسمَل"), () => {
				frappe.set_route("Form", "Asset Repair", frm.doc.asset_repair);
			}, __("المحاسبة"));
		}

		if (frm.doc.docstatus === 1 && !FINAL_STATUSES.includes(frm.doc.status)) {
			// يُصرَف تلقائياً (Stock Entry حقيقي) لحظة إتمام أمر العمل —
			// انظر Asset Work Order.complete_work_order() ->
			// _auto_issue_linked_spare_parts()، وليس هنا.
			frm.add_custom_button(__("طلب قطعة غيار لهذا الأمر"), () => {
				frappe.new_doc("Asset Spare Part Request", {
					asset: frm.doc.asset,
					asset_work_order: frm.doc.name,
				});
			}, __("المخزون"));
		}

		if (!frm.doc.failure_analysis) {
			frm.add_custom_button(__("تحليل سبب العطل (ISO 14224)"), () => {
				frappe.new_doc("Asset Failure Analysis", {
					asset: frm.doc.asset,
					work_order: frm.doc.name,
				});
			}, __("الموثوقية"));
		} else {
			frm.add_custom_button(__("عرض تحليل سبب العطل"), () => {
				frappe.set_route("Form", "Asset Failure Analysis", frm.doc.failure_analysis);
			}, __("الموثوقية"));
		}

		if (frm.doc.penalty_journal_entry) {
			frm.add_custom_button(__("مراجعة مسودة جزاء SLA"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.penalty_journal_entry);
			}, __("المحاسبة"));
		}
	},
});
