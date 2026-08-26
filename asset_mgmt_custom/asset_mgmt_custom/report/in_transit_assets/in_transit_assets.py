import frappe
from frappe import _


def execute(filters=None):
    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": _("Movement"), "fieldname": "movement", "fieldtype": "Link", "options": "Asset Movement", "width": 150},
        {"label": _("Source Location"), "fieldname": "source_location", "fieldtype": "Link", "options": "Location", "width": 140},
        {"label": _("Target Location"), "fieldname": "target_location", "fieldtype": "Link", "options": "Location", "width": 140},
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Data", "width": 130},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Data", "width": 110},
        {"label": _("Expected Arrival"), "fieldname": "expected_arrival", "fieldtype": "Datetime", "width": 150},
        {"label": _("Transaction Date"), "fieldname": "transaction_date", "fieldtype": "Datetime", "width": 150},
    ]

    data = frappe.db.sql("""
        SELECT
            ami.asset,
            ami.asset_name,
            ami.parent AS movement,
            ami.source_location,
            ami.target_location,
            am.custom_driver_name AS driver,
            am.custom_vehicle_number AS vehicle,
            am.custom_expected_arrival AS expected_arrival,
            am.transaction_date
        FROM `tabAsset Movement Item` ami
        JOIN `tabAsset Movement` am ON am.name = ami.parent
        JOIN `tabAsset` a ON a.name = ami.asset
        WHERE am.docstatus = 1
          AND am.purpose = 'Transfer'
          AND a.custom_operational_status = 'In Transit'
        ORDER BY am.transaction_date DESC
    """, as_dict=True)

    return columns, data
