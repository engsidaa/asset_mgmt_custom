"""
Asset Movement override
-----------------------
Validate:
  - Transfer: يشترط وجود tag (Sticker/Iron Code) على كل أصل قبل النقل
  - Transfer: يمنع نقل أصول بحالة Incomplete

On Submit:
  - Transfer / Receipt: تحديث cost_center في الأصل من حقل Location.custom_cost_center
  - Transfer: ضبط custom_operational_status = In Transit + إشعار
  - Receipt لأصل احتياطي: تفعيل الأصل + مسح حالة In Transit
  - تسجيل كل حدث في Asset Activity

On Cancel:
  - استعادة cost_center من الموقع الأصلي
  - إعادة حالة In Transit إلى Operational عند الإلغاء
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, now_datetime


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate(doc, method=None):
    if doc.purpose == "Transfer":
        _require_sticker_or_iron_code_for_transfer(doc)
        _block_incomplete_asset_transfer(doc)


def _require_sticker_or_iron_code_for_transfer(doc):
    for item in doc.assets:
        tag_type = frappe.db.get_value("Asset", item.asset, "custom_tag_type")
        sticker = frappe.db.get_value("Asset", item.asset, "custom_sticker_code")
        iron = frappe.db.get_value("Asset", item.asset, "custom_iron_code")
        asset_name = frappe.db.get_value("Asset", item.asset, "asset_name")

        if tag_type == "Iron Code" and not iron:
            frappe.throw(
                _("Asset <b>{0}</b> has no Iron Code. Assign it before transfer.").format(
                    asset_name or item.asset),
                title=_("Iron Code Required"),
            )
        elif tag_type in ("Barcode", "RFID") and not sticker:
            frappe.throw(
                _("Asset <b>{0}</b> has no Sticker Code. Assign it before transfer.").format(
                    asset_name or item.asset),
                title=_("Sticker Code Required"),
            )
        elif not tag_type and not sticker:
            frappe.throw(
                _("Asset <b>{0}</b> has no tag (Sticker Code or Iron Code). Assign before transfer.").format(
                    asset_name or item.asset),
                title=_("Tag Required for Transfer"),
            )


def _block_incomplete_asset_transfer(doc):
    for item in doc.assets:
        status = frappe.db.get_value("Asset", item.asset, "custom_operational_status")
        if status == "Incomplete":
            asset_name = frappe.db.get_value("Asset", item.asset, "asset_name")
            frappe.throw(
                _("Asset <b>{0}</b> is Incomplete. Set it to Operational before transferring.").format(
                    asset_name or item.asset),
                title=_("Asset Not Operational"),
            )


# ---------------------------------------------------------------------------
# On Submit
# ---------------------------------------------------------------------------

def on_submit(doc, method=None):
    if doc.purpose not in ("Transfer", "Receipt"):
        return

    for item in doc.assets:
        _update_cost_center(doc, item)
        _update_branch(item)

        if doc.purpose == "Transfer":
            _set_in_transit(item)
            _notify_target_location(doc, item)

        if doc.purpose == "Receipt":
            _activate_spare_asset(doc, item)
            _clear_transit(item)


def _set_in_transit(item):
    frappe.db.set_value("Asset", item.asset, "custom_operational_status", "In Transit", update_modified=False)
    _log_activity(item.asset, "Asset status changed to In Transit")


def _clear_transit(item):
    current = frappe.db.get_value("Asset", item.asset, "custom_operational_status")
    if current == "In Transit":
        frappe.db.set_value("Asset", item.asset, "custom_operational_status", "Operational", update_modified=False)
        _log_activity(item.asset, "Asset arrived and status set back to Operational")


def _get_assets_manager_emails():
    """Return email list of all enabled users holding the 'Assets Manager' role."""
    return [r[0] for r in frappe.db.sql("""
        SELECT u.email
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = 'Assets Manager'
          AND u.enabled = 1
          AND u.name NOT IN ('Administrator', 'All', 'Guest')
          AND u.email IS NOT NULL AND u.email != ''
    """)]


def _notify_target_location(doc, item):
    """Notify ALL users with 'Assets Manager' role when an asset enters transit."""
    try:
        target = item.target_location
        if not target:
            return

        recipients = _get_assets_manager_emails()
        if not recipients:
            return

        asset_name = frappe.db.get_value("Asset", item.asset, "asset_name") or item.asset
        driver = doc.get("custom_driver_name") or _("Unknown Driver")
        vehicle = doc.get("custom_vehicle_number") or "-"

        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
        enqueue_create_notification(
            users=recipients,
            doc=frappe._dict(
                subject=_("Asset {0} is In Transit to {1}").format(asset_name, target),
                email_content=_(
                    "Asset <b>{0}</b> is being transferred to <b>{1}</b>.<br>"
                    "Driver: {2} | Vehicle: {3}<br>"
                    "Movement: {4}"
                ).format(asset_name, target, driver, vehicle, doc.name),
                document_type="Asset Movement",
                document_name=doc.name,
                from_user=frappe.session.user,
                type="Alert",
            ),
        )
    except Exception:
        pass


def _update_cost_center(doc, item):
    target = item.target_location
    if not target:
        return
    cost_center = frappe.db.get_value("Location", target, "custom_cost_center")
    if not cost_center:
        return
    frappe.db.set_value("Asset", item.asset, "cost_center", cost_center, update_modified=False)
    _log_activity(item.asset, "Cost center updated to {0} after {1} to {2}".format(
        cost_center, doc.purpose, target))


def _update_branch(item):
    branch = item.get("custom_target_branch")
    if not branch:
        return
    frappe.db.set_value("Asset", item.asset, "custom_branch", branch, update_modified=False)
    _log_activity(item.asset, "Branch updated to {0}".format(branch))


def _activate_spare_asset(doc, item):
    is_spare = frappe.db.get_value("Asset", item.asset, "custom_is_spare")
    if not is_spare:
        return
    target = item.target_location
    activation_date = getdate(doc.transaction_date) if doc.transaction_date else getdate(nowdate())
    frappe.db.set_value("Asset", item.asset, {
        "custom_is_spare": 0,
        "available_for_use_date": activation_date,
    }, update_modified=False)
    _log_activity(item.asset, "Spare asset activated at location {0} on {1}. Enable depreciation.".format(
        target or "unknown", activation_date))
    frappe.msgprint(
        _("Asset <b>{0}</b> activated at <b>{1}</b>. Please enable depreciation.").format(
            item.asset, target or "unknown"),
        title=_("Spare Asset Activated"), indicator="blue",
    )


def _log_activity(asset, subject):
    """تسجيل حدث في Asset Activity."""
    try:
        frappe.get_doc({
            "doctype": "Asset Activity",
            "asset": asset,
            "subject": subject,
            "user": frappe.session.user,
            "date": now_datetime(),
        }).insert(ignore_permissions=True, ignore_links=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# On Cancel
# ---------------------------------------------------------------------------

def on_cancel(doc, method=None):
    if doc.purpose not in ("Transfer", "Receipt"):
        return
    for item in doc.assets:
        _revert_cost_center(item)
        if doc.purpose == "Transfer":
            _revert_transit(item)


def _revert_transit(item):
    current = frappe.db.get_value("Asset", item.asset, "custom_operational_status")
    if current == "In Transit":
        frappe.db.set_value("Asset", item.asset, "custom_operational_status", "Operational", update_modified=False)


def _revert_cost_center(item):
    source = item.source_location
    if not source:
        return
    cost_center = frappe.db.get_value("Location", source, "custom_cost_center")
    if not cost_center:
        return
    frappe.db.set_value("Asset", item.asset, "cost_center", cost_center, update_modified=False)
    _log_activity(item.asset, "Cost center reverted to {0} after cancellation".format(cost_center))


# ---------------------------------------------------------------------------
# Confirm Receipt (whitelist)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def confirm_receipt(movement_name):
    """
    Called by the receiving branch manager to confirm physical receipt.
    Changes each asset from 'In Transit' to 'Operational'.
    """
    doc = frappe.get_doc("Asset Movement", movement_name)
    if doc.purpose != "Transfer":
        frappe.throw(_("Confirm Receipt is only for Transfer movements."))
    if doc.docstatus != 1:
        frappe.throw(_("Movement must be submitted."))

    confirmed = []
    for item in doc.assets:
        status = frappe.db.get_value("Asset", item.asset, "custom_operational_status")
        if status == "In Transit":
            frappe.db.set_value("Asset", item.asset, {
                "custom_operational_status": "Operational",
            }, update_modified=False)
            _log_activity(item.asset, "Asset receipt confirmed at {0}. Status: Operational.".format(
                item.target_location or "destination"))
            confirmed.append(item.asset)

    if confirmed:
        frappe.db.set_value("Asset Movement", movement_name, "custom_receipt_confirmed", 1, update_modified=False)

    return confirmed
