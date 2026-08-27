frappe.ui.form.on("Asset Handover", {
    refresh(frm) {
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Print Handover Certificate"), () => {
                frappe.utils.print(
                    frm.doctype,
                    frm.docname,
                    "Asset Handover Certificate"
                );
            }, __("Print"));
        }

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Fetch Branch Assets"), () => {
                if (!frm.doc.branch) {
                    frappe.msgprint(__("Please select a Branch first."));
                    return;
                }
                frappe.call({
                    method: "asset_mgmt_custom.asset_mgmt_custom.doctype.asset_handover.asset_handover.fetch_branch_assets",
                    args: { branch: frm.doc.branch },
                    callback(r) {
                        if (r.message && r.message.length) {
                            frm.clear_table("items");
                            r.message.forEach(a => {
                                let row = frm.add_child("items");
                                row.asset = a.name;
                                row.asset_name = a.asset_name;
                                row.asset_category = a.asset_category;
                                row.serial_no = a.serial_no;
                                row.condition = "Good";
                            });
                            frm.refresh_field("items");
                            frappe.show_alert({
                                message: __("{0} assets loaded from branch.", [r.message.length]),
                                indicator: "green"
                            });
                        } else {
                            frappe.msgprint(__("No active assets found for this branch."));
                        }
                    }
                });
            });
        }
    }
});
