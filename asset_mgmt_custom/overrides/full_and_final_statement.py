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
