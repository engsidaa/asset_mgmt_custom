import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class AssetSparePart(Document):
    pass


@frappe.whitelist()
def complete_refurbishment(spare_part, serial_no, refurbishment_cost=0):
    """
    يُغلِق دورة القطعة الدوارة (Rotable): وحدة تالفة استُلمت سابقاً في
    مستودع "استلام الأعطاب" (انظر Asset Spare Part Request.
    _receive_failed_core_unit) وتم تجديدها فعلياً خارج النظام (ورشة
    داخلية أو مورد خارجي) — تُنقَل الآن كمخزون صالح للاستخدام مرة أخرى
    إلى المستودع الرئيسي، بتكلفة التجديد الفعلية (وليس صفراً كما استُلمت
    تالفة) عبر Stock Entry واحدة من نوع Material Transfer تُعيد تقييم
    الوحدة عند الاستلام في المستودع الرئيسي — بدل معاملتها كقطعة جديدة
    مُشتراة من الصفر.
    """
    part = frappe.get_doc("Asset Spare Part", spare_part)
    if not part.is_rotable:
        frappe.throw(_("Asset Spare Part {0} is not marked as rotable.").format(spare_part))
    if not part.core_return_warehouse or not part.warehouse:
        frappe.throw(_("Both the core-return warehouse and the main warehouse must be set on {0}.").format(spare_part))
    if flt(part.pending_refurbishment_qty) <= 0:
        frappe.throw(_("No units are currently pending refurbishment for {0}.").format(spare_part))

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Transfer"
    se.company = frappe.defaults.get_user_default("Company")
    se.posting_date = today()
    se.remarks = _("Refurbishment completed for rotable spare part {0}, serial {1}").format(spare_part, serial_no)

    se.append("items", {
        "item_code": part.item_code,
        "qty": 1,
        "s_warehouse": part.core_return_warehouse,
        "t_warehouse": part.warehouse,
        "serial_no": serial_no,
        "basic_rate": flt(refurbishment_cost),
    })

    se.insert(ignore_permissions=True)
    se.submit()

    frappe.db.set_value(
        "Asset Spare Part", spare_part,
        {
            "quantity": flt(part.quantity) + 1,
            "pending_refurbishment_qty": max(flt(part.pending_refurbishment_qty) - 1, 0),
        },
        update_modified=False,
    )

    frappe.msgprint(
        _("Refurbishment complete — unit returned to serviceable stock via {0}.").format(se.name),
        alert=True, indicator="green",
    )
    return se.name
