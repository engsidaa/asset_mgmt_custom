frappe.ui.form.on("Asset Work Permit", {
	refresh(frm) {
		if (frm.doc.requires_loto && !frm.doc.loto_verified) {
			frm.add_custom_button(__("توقيع اكتمال عزل الطاقة (LOTO)"), () => {
				frappe.confirm(
					__("بتوقيعك، أنت تؤكد اكتمال جميع خطوات عزل الطاقة فعلياً على أرض الواقع. متابعة؟"),
					() => {
						frappe.call({
							method: "complete_loto_checklist",
							doc: frm.doc,
							freeze: true,
							callback(r) {
								if (r.message) frm.reload_doc();
							},
						});
					}
				);
			}, __("السلامة"));
		}
	}
});
