"""
Full and Final Statement override
----------------------------------
Adds an early validation (at 'validate') that warns if the employee
still has assets allocated. HRMS already blocks at before_submit;
this gives a visible warning before the user tries to submit.
"""

import frappe
from frappe import _


def validate(doc, method=None):
    _warn_pending_assets(doc)


def on_submit(doc, method=None):
    _create_asset_return_requests(doc)


def _warn_pending_assets(doc):
    employee = doc.employee
    if not employee:
        return

    # Count assets currently under this employee's custody (docstatus=1 movements)
    allocated = frappe.db.sql("""
        SELECT COUNT(DISTINCT asm_item.asset) AS cnt
        FROM `tabAsset Movement Item` asm_item
        JOIN `tabAsset Movement` asm ON asm.name = asm_item.parent
        WHERE asm.docstatus = 1
          AND asm_item.to_employee = %(employee)s
          AND asm_item.asset NOT IN (
              SELECT ri.asset FROM `tabAsset Movement Item` ri
              JOIN `tabAsset Movement` rm ON rm.name = ri.parent
              WHERE rm.docstatus = 1
                AND ri.from_employee = %(employee)s
          )
    """, {"employee": employee}, as_dict=True)

    count = allocated[0].cnt if allocated else 0
    if count:
        frappe.msgprint(
            _("Employee <b>{0}</b> still has <b>{1}</b> asset(s) allocated. "
              "All assets must be returned before submitting the Final Settlement.").format(
                employee, count),
            title=_("Pending Asset Returns"),
            indicator="orange",
        )


def _create_asset_return_requests(doc):
    """On Full & Final submission: notify Assets Managers to collect employee assets."""
    employee = doc.employee
    if not employee:
        return

    allocated = frappe.db.sql("""
        SELECT DISTINCT asm_item.asset, a.asset_name
        FROM `tabAsset Movement Item` asm_item
        JOIN `tabAsset Movement` asm ON asm.name = asm_item.parent
        JOIN `tabAsset` a ON a.name = asm_item.asset
        WHERE asm.docstatus = 1
          AND asm_item.to_employee = %(employee)s
          AND asm_item.asset NOT IN (
              SELECT ri.asset FROM `tabAsset Movement Item` ri
              JOIN `tabAsset Movement` rm ON rm.name = ri.parent
              WHERE rm.docstatus = 1
                AND ri.from_employee = %(employee)s
          )
    """, {"employee": employee}, as_dict=True)

    if not allocated:
        return

    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    managers = [r[0] for r in frappe.db.sql("""
        SELECT u.name
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Assets Manager' AND u.enabled = 1
    """)]

    asset_list = ", ".join(f"<b>{a.asset_name or a.asset}</b>" for a in allocated)
    enqueue_create_notification(
        users=managers,
        doc=frappe._dict(
            subject=_("Employee {0} offboarded — {1} asset(s) to collect").format(
                employee, len(allocated)),
            email_content=_("Full & Final Statement submitted for employee <b>{0}</b>. "
                            "The following assets must be collected: {1}").format(
                employee, asset_list),
            document_type="Full and Final Statement",
            document_name=doc.name,
            from_user=frappe.session.user,
            type="Alert",
        ),
    )
