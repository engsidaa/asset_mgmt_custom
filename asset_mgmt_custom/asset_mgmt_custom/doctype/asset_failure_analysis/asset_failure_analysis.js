frappe.ui.form.on("Asset Failure Analysis", {
	refresh(frm) {
		if (frm.doc.failure_mode) {
			frm.add_custom_button(__("اقتراحات حلول سابقة"), () => {
				frappe.call({
					method: "asset_mgmt_custom.asset_mgmt_custom.doctype.asset_failure_analysis.asset_failure_analysis.get_suggested_remedies",
					args: {
						failure_mode: frm.doc.failure_mode,
						problem_code: frm.doc.problem_code,
						exclude: frm.doc.name,
					},
					freeze: true,
					callback(r) {
						const rows = r.message || [];
						if (!rows.length) {
							frappe.msgprint(__("لا توجد حالات سابقة مسجَّلة بنفس تركيبة رمز المشكلة/السبب هذه."));
							return;
						}
						const html = rows.map((row) => `
							<div style="padding: 8px 0; border-bottom: 1px solid var(--border-color);">
								<b>${frappe.utils.escape_html(row.remedy_code)}</b>
								${row.example_detail ? `<div style="font-size: 12px;">${frappe.utils.escape_html(row.example_detail)}</div>` : ''}
								<div class="text-muted" style="font-size: 12px;">
									${__("استُخدم")} ${row.count} ${__("مرة")} — ${__("آخر مرة")}: ${frappe.datetime.str_to_user(row.last_used) || row.last_used}
								</div>
							</div>
						`).join("");
						frappe.msgprint({
							title: __("إجراءات تصحيحية شائعة لنفس نمط العطل"),
							message: `<div dir="rtl">${html}</div>`,
							wide: true,
						});
					}
				});
			}, __("قاعدة المعرفة"));
		}
	}
});
