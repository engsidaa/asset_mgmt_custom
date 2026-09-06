frappe.ui.form.on("Asset Spare Part", {
	refresh(frm) {
		if (frm.doc.is_rotable && flt(frm.doc.pending_refurbishment_qty) > 0) {
			frm.add_custom_button(__("إتمام تجديد وحدة"), () => {
				frappe.prompt(
					[
						{
							fieldname: "serial_no",
							fieldtype: "Data",
							label: __("الرقم التسلسلي للوحدة المُجدَّدة"),
							reqd: 1,
						},
						{
							fieldname: "refurbishment_cost",
							fieldtype: "Currency",
							label: __("تكلفة التجديد الفعلية"),
						},
					],
					(values) => {
						frappe.call({
							method: "asset_mgmt_custom.asset_mgmt_custom.doctype.asset_spare_part.asset_spare_part.complete_refurbishment",
							args: {
								spare_part: frm.doc.name,
								serial_no: values.serial_no,
								refurbishment_cost: values.refurbishment_cost || 0,
							},
							freeze: true,
							callback(r) {
								if (r.message) frm.reload_doc();
							},
						});
					},
					__("إتمام تجديد قطعة دوارة"),
					__("تأكيد")
				);
			}, __("قطع الغيار الدوارة"));
		}
	}
});
