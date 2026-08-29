"""
Full and Final Statement override
----------------------------------
HRMS core already implements the hard custody-clearance gate: its own
validate_assets() (before_submit) blocks submission while any allocated
asset has action='Return' and status='Owned', and its own
get_assets_movement() auto-populates the assets_allocated table from real
Asset Movement records. We don't duplicate any of that here.

What HRMS has no concept of: an employee travelling abroad with an
approved Asset Retention Request should NOT be blocked the same way as
someone who simply hasn't returned an asset. This override adds exactly
that one exemption, and a post-submit notification (HRMS doesn't send one).

validate (runs AFTER HRMS's own validate(), which already populated
assets_allocated):
  - exempt_retained_assets: for any row covered by a currently-active,
    Approved Asset Retention Request, flip action to 'Recover Cost' with
    cost=0 so HRMS's own before_submit check doesn't block it — without
    touching HRMS's code.

on_submit:
  - notify Asset Managers about any 'Recover Cost' assets — HRMS's own
    before_submit gate guarantees no 'Return'-pending rows survive to this
    point, but a recovered-cost row means the asset is effectively lost or
    damaged and still needs real follow-up (write-off, status update) in
    the Asset module itself, which HRMS has no reason to know about.
"""

import frappe
from frappe import _
from frappe.utils import today


def validate(doc, method=None):
    _exempt_retained_assets(doc)


def on_submit(doc, method=None):
    _notify_assets_managers(doc)


def _exempt_retained_assets(doc):
    if not doc.employee or not doc.get("assets_allocated"):
        return

    retained_assets = _get_actively_retained_assets(doc.employee)
    if not retained_assets:
        return

    for row in doc.assets_allocated:
        if row.status != "Owned" or row.action != "Return":
            continue

        asset = _asset_for_row(row, doc.employee)
        if asset and asset in retained_assets:
            row.action = "Recover Cost"
            row.cost = 0
            row.description = _(
                "Retained under an approved Asset Retention Request "
                "({0}) while travelling — not treated as unreturned."
            ).format(retained_assets[asset])


def _get_actively_retained_assets(employee):
    """Asset -> Asset Retention Request name, for Approved requests whose
    travel period is still current (or open-ended, no travel_end set)."""
    rows = frappe.get_all(
        "Asset Retention Request",
        filters={
            "employee": employee,
            "status": "Approved",
            "docstatus": ["!=", 2],
        },
        fields=["name", "asset", "travel_end"],
    )
    today_ = today()
    return {
        r.asset: r.name
        for r in rows
        if r.asset and (not r.travel_end or str(r.travel_end) >= today_)
    }


def _asset_for_row(row, employee):
    """assets_allocated rows carry `reference` (Asset Movement) and a plain
    text `asset_name`, not an Asset link — recover the actual Asset the
    same way HRMS's own get_assets_movement() built the row."""
    if not row.reference:
        return None
    return frappe.db.get_value(
        "Asset Movement Item",
        {"parent": row.reference, "to_employee": employee},
        "asset",
    )


def _notify_assets_managers(doc):
    """On Full & Final submission: notify Asset Managers about any
    'Recover Cost' rows — the asset is effectively written off from the
    employee's custody, but its status/write-off in the Asset module
    itself needs a human to actually action it."""
    recovered = [
        row for row in doc.get("assets_allocated", [])
        if row.action == "Recover Cost" and row.cost
    ]
    if not recovered:
        return

    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    managers = [r[0] for r in frappe.db.sql("""
        SELECT u.name
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Asset Manager' AND u.enabled = 1
    """)]
    if not managers:
        return

    asset_list = ", ".join(f"<b>{row.asset_name or row.reference}</b>" for row in recovered)
    enqueue_create_notification(
        users=managers,
        doc=frappe._dict(
            subject=_("Employee {0} offboarded — {1} asset(s) need write-off follow-up").format(
                doc.employee, len(recovered)),
            email_content=_("Full & Final Statement submitted for employee <b>{0}</b>. "
                            "Cost was recovered instead of the asset being returned for: {1}. "
                            "Please update these assets' status / process a write-off.").format(
                doc.employee, asset_list),
            document_type="Full and Final Statement",
            document_name=doc.name,
            from_user=frappe.session.user,
            type="Alert",
        ),
    )
