"""
Asset Movement override
-----------------------
عند تقديم سند تحويل أصل:
  - يُحدِّث cost_center في الأصل من حقل cost_center الموجود على Location
  - يُسجَّل في asset_activity
"""

import frappe
from frappe import _
from frappe.utils import getdate


def on_submit(doc, method=None):
    """تحديث مركز التكلفة على الأصل عند النقل لموقع جديد."""
    if doc.purpose not in ("Transfer", "Receipt"):
        return

    for item in doc.assets:
        target = item.target_location
        if not target:
            continue

        cost_center = frappe.db.get_value("Location", target, "custom_cost_center")
        if not cost_center:
            continue

        asset = frappe.get_doc("Asset", item.asset)
        asset.cost_center = cost_center
        asset.flags.ignore_validate_update_after_submit = True
        asset.db_set("cost_center", cost_center, update_modified=False)

        frappe.get_doc(
            {
                "doctype": "Asset Activity",
                "asset": item.asset,
                "activity_type": "Transfer",
                "date": getdate(),
                "notes": _(
                    "Cost center updated to {0} after transfer to location {1}"
                ).format(cost_center, target),
            }
        ).insert(ignore_permissions=True)


def on_cancel(doc, method=None):
    """استعادة مركز التكلفة السابق عند إلغاء سند التحويل."""
    if doc.purpose not in ("Transfer", "Receipt"):
        return

    for item in doc.assets:
        source = item.source_location
        if not source:
            continue

        cost_center = frappe.db.get_value("Location", source, "custom_cost_center")
        if not cost_center:
            continue

        frappe.db.set_value(
            "Asset", item.asset, "cost_center", cost_center, update_modified=False
        )
