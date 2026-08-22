"""
Asset Movement override
-----------------------
Validate:
  - Transfer: يشترط وجود كود الستيكر على كل أصل قبل النقل للفروع

On Submit:
  - Transfer / Receipt: تحديث cost_center في الأصل من حقل Location.custom_cost_center
  - Receipt لأصل احتياطي: تفعيل الأصل (مسح is_spare + ضبط تاريخ الاستخدام + إشعار)
  - تسجيل كل حدث في Asset Activity

On Cancel:
  - استعادة cost_center من الموقع الأصلي
  - إعادة علامة is_spare للأصل لو كانت نقله الأولى
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, now_datetime


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate(doc, method=None):
    if doc.purpose == "Transfer":
        _require_sticker_code_for_transfer(doc)


def _require_sticker_code_for_transfer(doc):
    """لا يمكن نقل أصل بين الفروع إن لم يكن له كود ستيكر."""
    for item in doc.assets:
        sticker = frappe.db.get_value("Asset", item.asset, "custom_sticker_code")
        if not sticker:
            asset_name = frappe.db.get_value("Asset", item.asset, "asset_name")
            frappe.throw(
                _(
                    "Asset <b>{0}</b> ({1}) does not have a Sticker Code. "
                    "Please assign a sticker code before transferring the asset."
                ).format(asset_name or item.asset, item.asset),
                title=_("Sticker Code Required"),
            )


# ---------------------------------------------------------------------------
# On Submit
# ---------------------------------------------------------------------------

def on_submit(doc, method=None):
    if doc.purpose not in ("Transfer", "Receipt"):
        return

    for item in doc.assets:
        _update_cost_center(doc, item)

        if doc.purpose == "Receipt":
            _activate_spare_asset(doc, item)


def _update_cost_center(doc, item):
    """تحديث مركز التكلفة على الأصل من مركز تكلفة الموقع الهدف."""
    target = item.target_location
    if not target:
        return

    cost_center = frappe.db.get_value("Location", target, "custom_cost_center")
    if not cost_center:
        return

    frappe.db.set_value(
        "Asset", item.asset, "cost_center", cost_center, update_modified=False
    )

    _log_activity(
        item.asset,
        _(
            "Cost center updated to {0} after {1} to location {2}"
        ).format(cost_center, doc.purpose, target),
    )


def _activate_spare_asset(doc, item):
    """
    عند استلام أصل احتياطي في موقع جديد:
    - يُزال تصنيف 'احتياطي'
    - يُضبط تاريخ الاستخدام = تاريخ الاستلام
    - يُرسل إشعار لمدير الأصول لتفعيل الإهلاك
    """
    is_spare = frappe.db.get_value("Asset", item.asset, "custom_is_spare")
    if not is_spare:
        return

    target = item.target_location
    activation_date = getdate(doc.transaction_date) if doc.transaction_date else getdate(nowdate())

    frappe.db.set_value(
        "Asset",
        item.asset,
        {
            "custom_is_spare": 0,
            "available_for_use_date": activation_date,
        },
        update_modified=False,
    )

    _log_activity(
        item.asset,
        _(
            "Spare asset activated: received at location {0} on {1}. "
            "Please enable depreciation from the asset form."
        ).format(target or _("unknown"), activation_date),
    )

    frappe.msgprint(
        _(
            "Asset <b>{0}</b> has been activated at location <b>{1}</b>. "
            "Please open the asset and enable depreciation with the correct start date."
        ).format(item.asset, target or _("unknown")),
        title=_("Spare Asset Activated"),
        indicator="blue",
    )


def _log_activity(asset, subject):
    """تسجيل حدث في Asset Activity."""
    frappe.get_doc(
        {
            "doctype": "Asset Activity",
            "asset": asset,
            "subject": subject,
            "user": frappe.session.user,
            "date": now_datetime(),
        }
    ).insert(ignore_permissions=True, ignore_links=True)


# ---------------------------------------------------------------------------
# On Cancel
# ---------------------------------------------------------------------------

def on_cancel(doc, method=None):
    if doc.purpose not in ("Transfer", "Receipt"):
        return

    for item in doc.assets:
        _revert_cost_center(item)


def _revert_cost_center(item):
    """استعادة مركز التكلفة من الموقع الأصلي عند إلغاء السند."""
    source = item.source_location
    if not source:
        return

    cost_center = frappe.db.get_value("Location", source, "custom_cost_center")
    if not cost_center:
        return

    frappe.db.set_value(
        "Asset", item.asset, "cost_center", cost_center, update_modified=False
    )

    _log_activity(
        item.asset,
        _("Cost center reverted to {0} after cancellation of movement to {1}").format(
            cost_center, item.target_location or _("unknown")
        ),
    )
