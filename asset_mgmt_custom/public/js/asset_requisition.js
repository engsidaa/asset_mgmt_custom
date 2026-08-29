// Client Script – Asset Requisition Form
// مصفوفة الاعتماد: المالية ← مدير الفرع ← إدارة الأصول (بالترتيب)

const APPROVAL_STAGES = {
	"Pending Finance Approval": {
		method: "approve_finance",
		label: __("Approve (Finance)"),
		can_act: (frm) => frappe.user_roles.includes("Asset Finance Manager") || frappe.user_roles.includes("System Manager"),
	},
	"Pending Branch Manager Approval": {
		method: "approve_branch_manager",
		label: __("Approve (Branch Manager)"),
		can_act: (frm) =>
			(frm.doc.branch_manager && frappe.session.user === frm.doc.branch_manager) ||
			frappe.user_roles.includes("System Manager"),
	},
	"Pending Asset Manager Approval": {
		method: "approve_asset_manager",
		label: __("Approve (Asset Manager)"),
		can_act: (frm) => frappe.user_roles.includes("Asset Manager") || frappe.user_roles.includes("System Manager"),
	},
};

function _add_approval_buttons(frm) {
	if (frm.doc.docstatus !== 1) return;

	const stage = APPROVAL_STAGES[frm.doc.status];
	if (!stage) return;

	if (!stage.can_act(frm)) {
		frm.dashboard.add_comment(
			__("Waiting for approval at this stage. You do not have the required role/identity to act."),
			"orange"
		);
		return;
	}

	frm.add_custom_button(stage.label, function () {
		frappe.confirm(
			__("Approve this requisition at the current stage?"),
			function () {
				frappe.call({
					method: stage.method,
					doc: frm.doc,
					freeze: true,
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Approved. Moved to: {0}", [r.message]), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			}
		);
	}, __("Actions")).addClass("btn-primary");

	frm.add_custom_button(__("Reject"), function () {
		frappe.prompt(
			{ fieldname: "reason", label: __("Rejection Reason"), fieldtype: "Small Text", reqd: 1 },
			function (values) {
				frappe.call({
					method: "reject",
					doc: frm.doc,
					args: { reason: values.reason },
					freeze: true,
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Requisition rejected."), indicator: "red" });
							frm.reload_doc();
						}
					},
				});
			},
			__("Reject Requisition")
		);
	}, __("Actions"));
}

frappe.ui.form.on("Asset Requisition", {
	refresh(frm) {
		_add_approval_buttons(frm);

		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && frm.doc.spare_available) {
			frm.add_custom_button(__("Create Asset Movement"), function () {
				frappe.call({
					method: "create_asset_movement",
					doc: frm.doc,
					callback(r) {
						if (r.message) {
							frappe.set_route("Form", "Asset Movement", r.message);
						}
					},
				});
			}, __("Actions"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.spare_available) {
			frm.add_custom_button(__("Create Purchase Request"), function () {
				frappe.call({
					method: "create_purchase_requisition",
					doc: frm.doc,
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: __("Material Request created: {0}", [r.message]), indicator: "green" });
							frappe.set_route("Form", "Material Request", r.message);
						}
					}
				});
			}, __("Actions"));
		}

		if (frm.doc.spare_available) {
			frm.dashboard.add_comment(
				__("Spare asset available: {0}", [frm.doc.spare_asset]),
				"green"
			);
		} else if (frm.doc.docstatus === 0) {
			frm.dashboard.add_comment(
				__("No spare asset found for this category. A purchase requisition may be needed."),
				"orange"
			);
		}
	},

	asset_category(frm) {
		if (frm.doc.asset_category) {
			frm.save();
		}
	},
});
