"""
API السائق — Asset Movement (نقل الأصول).

السائق يتلقى Asset Movements مُسنَدة له عبر حقل custom_driver_employee،
يُؤكِّد استلام الأصل من المخزن المصدر (pickup)، ثم يُؤكِّد تسليمه
للوجهة (delivery) — ما يُكمِل الحركة فعلياً في النظام.

الأمان: كل endpoint يتحقق أن المستخدم الحالي هو الموظف المُعيَّن سائقاً.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today


def _get_driver_employee(user=None):
    user = user or frappe.session.user
    emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not emp:
        frappe.throw(_("لم يتم ربط حساب المستخدم بسجل موظف."), frappe.PermissionError)
    roles = frappe.get_roles(user)
    if "Driver" not in roles and "System Manager" not in roles:
        frappe.throw(_("هذه الوظيفة مخصصة للسائقين فقط."), frappe.PermissionError)
    return emp


def _assert_movement_driver(movement_name, emp):
    assigned = frappe.db.get_value(
        "Asset Movement", movement_name, "custom_driver_employee"
    )
    if assigned != emp:
        frappe.throw(
            _("حركة الأصل {0} غير مُسنَدة إليك.").format(movement_name),
            frappe.PermissionError,
        )


# ---------------------------------------------------------------------------
# قائمة حركات الأصول لليوم
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_driver_asset_movements(movement_date=None):
    """
    قائمة حركات الأصول المُسنَدة للسائق في تاريخ معيَّن.
    تشمل: اسم الأصل، الموقع المصدر والوجهة، الحالة الحالية.
    """
    emp = _get_driver_employee()
    d = movement_date or today()

    movements = frappe.db.sql(
        """
        SELECT
            am.name,
            am.transaction_date,
            am.purpose,
            am.custom_transit_status,
            am.custom_pickup_datetime,
            am.custom_delivery_datetime,
            am.custom_transit_notes,
            GROUP_CONCAT(DISTINCT ami.asset ORDER BY ami.asset SEPARATOR '، ') AS assets_summary,
            GROUP_CONCAT(DISTINCT ami.asset_name ORDER BY ami.asset SEPARATOR '، ') AS asset_names_summary,
            COUNT(ami.asset) AS asset_count,
            MIN(ami.source_location) AS source_location,
            MIN(ami.target_location) AS target_location
        FROM `tabAsset Movement` am
        JOIN `tabAsset Movement Item` ami ON ami.parent = am.name
        WHERE am.custom_driver_employee = %(emp)s
          AND DATE(am.transaction_date) = %(d)s
          AND am.docstatus = 1
        GROUP BY am.name
        ORDER BY am.transaction_date
        """,
        {"emp": emp, "d": d},
        as_dict=True,
    )

    return {
        "date": d,
        "driver_employee": emp,
        "movements": movements,
        "pending_count": sum(
            1 for m in movements if m.get("custom_transit_status") in ("Pending", None, "")
        ),
    }


@frappe.whitelist()
def get_movement_details(movement_name):
    """تفاصيل حركة أصل واحدة للسائق."""
    emp = _get_driver_employee()
    _assert_movement_driver(movement_name, emp)

    doc = frappe.db.get_value(
        "Asset Movement",
        movement_name,
        ["name", "transaction_date", "purpose", "custom_transit_status",
         "custom_driver_employee", "custom_driver_name", "custom_vehicle_number",
         "custom_pickup_datetime", "custom_pickup_photo",
         "custom_delivery_datetime", "custom_delivery_photo",
         "custom_transit_notes", "docstatus"],
        as_dict=True,
    )
    if not doc:
        frappe.throw(_("حركة الأصل {0} غير موجودة.").format(movement_name))

    assets = frappe.db.sql(
        """
        SELECT ami.asset, ami.asset_name,
               ami.source_location, ami.target_location,
               ami.from_employee, ami.to_employee,
               a.custom_branch
        FROM `tabAsset Movement Item` ami
        LEFT JOIN `tabAsset` a ON a.name = ami.asset
        WHERE ami.parent = %(name)s
        ORDER BY ami.idx
        """,
        {"name": movement_name},
        as_dict=True,
    )

    return {"movement": doc, "assets": assets}


# ---------------------------------------------------------------------------
# تأكيد استلام الأصل (Pickup)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def confirm_asset_pickup(movement_name, photo_url="", notes=""):
    """
    السائق يُؤكِّد أنه استلم الأصل من المخزن المصدر.
    يُحدِّث custom_transit_status → In Transit ويُسجِّل وقت وصورة الاستلام.
    """
    emp = _get_driver_employee()
    _assert_movement_driver(movement_name, emp)

    current_status = frappe.db.get_value(
        "Asset Movement", movement_name, "custom_transit_status"
    )
    if current_status not in ("Pending", None, ""):
        frappe.throw(
            _("لا يمكن تأكيد الاستلام — الحالة الحالية: {0}").format(current_status or "—")
        )

    updates = {
        "custom_transit_status": "In Transit",
        "custom_pickup_datetime": now_datetime(),
    }
    if notes:
        updates["custom_transit_notes"] = notes
    if photo_url:
        updates["custom_pickup_photo"] = photo_url

    frappe.db.set_value("Asset Movement", movement_name, updates, update_modified=True)

    _notify_logistics(
        movement_name,
        f"السائق {emp} استلم الأصل — الرحلة بدأت",
    )

    return {"status": "In Transit", "pickup_at": str(updates["custom_pickup_datetime"])}


# ---------------------------------------------------------------------------
# تأكيد تسليم الأصل (Delivery)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def confirm_asset_delivery(movement_name, photo_url="", notes="", recipient_name=""):
    """
    السائق يُؤكِّد تسليم الأصل للمستلم في الوجهة.
    يُحدِّث custom_transit_status → Delivered، ويستدعي confirm_receipt
    من asset_mgmt_custom لتحديث custom_branch على الأصل.
    """
    emp = _get_driver_employee()
    _assert_movement_driver(movement_name, emp)

    current_status = frappe.db.get_value(
        "Asset Movement", movement_name, "custom_transit_status"
    )
    if current_status != "In Transit":
        frappe.throw(
            _("لا يمكن تأكيد التسليم قبل تأكيد الاستلام من المخزن المصدر.")
        )

    updates = {
        "custom_transit_status": "Delivered",
        "custom_delivery_datetime": now_datetime(),
        "custom_receipt_confirmed": 1,
    }
    if photo_url:
        updates["custom_delivery_photo"] = photo_url
    if notes:
        existing = frappe.db.get_value("Asset Movement", movement_name, "custom_transit_notes") or ""
        updates["custom_transit_notes"] = (existing + "\n" + notes).strip()

    frappe.db.set_value("Asset Movement", movement_name, updates, update_modified=True)

    # استدعاء منطق confirm_receipt الموجود مسبقاً لتحديث custom_branch على الأصل
    try:
        from asset_mgmt_custom.asset_mgmt_custom.api.branch_manager import confirm_receipt
        confirm_receipt(movement_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"driver confirm_receipt failed: {movement_name}")

    _notify_logistics(
        movement_name,
        f"السائق {emp} سلَّم الأصل — مكتمل",
    )

    return {
        "status": "Delivered",
        "delivery_at": str(updates["custom_delivery_datetime"]),
    }


# ---------------------------------------------------------------------------
# استثناء أثناء النقل
# ---------------------------------------------------------------------------

@frappe.whitelist()
def report_movement_exception(movement_name, reason, photo_url=""):
    """
    السائق يُبلِّغ عن مشكلة أثناء نقل الأصل (حادث، رفض الاستلام، إلخ).
    """
    emp = _get_driver_employee()
    _assert_movement_driver(movement_name, emp)

    existing = frappe.db.get_value(
        "Asset Movement", movement_name, "custom_transit_notes"
    ) or ""
    note = f"[استثناء — {now_datetime()}] {reason}"

    frappe.db.set_value(
        "Asset Movement",
        movement_name,
        {
            "custom_transit_status": "Exception",
            "custom_transit_notes": (existing + "\n" + note).strip(),
            **({"custom_delivery_photo": photo_url} if photo_url else {}),
        },
        update_modified=True,
    )

    _notify_logistics(
        movement_name,
        f"⚠ استثناء نقل أصل — {emp}: {reason}",
    )

    return {"status": "Exception"}


# ---------------------------------------------------------------------------
# internal helper
# ---------------------------------------------------------------------------

def _notify_logistics(movement_name, message):
    try:
        from asset_mgmt_custom.asset_mgmt_custom.utils.notification_hub import notify_role
        notify_role(
            role="Asset Manager",
            subject=f"تحديث نقل أصل — {movement_name}",
            message=message,
            doc_type="Asset Movement",
            doc_name=movement_name,
        )
    except Exception:
        pass
