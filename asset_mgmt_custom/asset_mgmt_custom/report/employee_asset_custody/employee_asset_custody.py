import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 170},
        {"label": _("Since"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Value"), "fieldname": "cost", "fieldtype": "Currency", "width": 120},
        {"label": _("Retention Approved?"), "fieldname": "retention_status", "fieldtype": "Data", "width": 140},
    ]


def get_data(filters):
    """Same 'still in custody' logic HRMS's own get_assets_movement() uses:
    an asset is currently held by an employee when their inward transfer
    count exceeds their outward transfer count."""
    emp_cond = ""
    values = {}
    if filters.get("employee"):
        emp_cond = "AND (asm_item.to_employee = %(employee)s OR asm_item.from_employee = %(employee)s)"
        values["employee"] = filters["employee"]

    movements = frappe.db.sql(
        f"""
        SELECT asm_item.asset, asm_item.asset_name, asm_item.from_employee, asm_item.to_employee,
               asm.transaction_date, asm.name AS movement
        FROM `tabAsset Movement Item` asm_item
        JOIN `tabAsset Movement` asm ON asm.name = asm_item.parent
        WHERE asm.docstatus = 1
          AND (asm_item.to_employee IS NOT NULL OR asm_item.from_employee IS NOT NULL)
          {emp_cond}
        ORDER BY asm.transaction_date
        """,
        values,
        as_dict=True,
    )

    inward, outward = {}, {}
    for m in movements:
        if m.to_employee:
            inward.setdefault((m.to_employee, m.asset), []).append(m)
        if m.from_employee:
            outward.setdefault((m.from_employee, m.asset), []).append(m)

    rows = []
    for (employee, asset), in_moves in inward.items():
        out_count = len(outward.get((employee, asset), []))
        if len(in_moves) <= out_count:
            continue  # already handed back

        latest = in_moves[-1]
        cost = frappe.db.get_value("Asset", asset, "total_asset_cost")
        emp_name, department = frappe.db.get_value(
            "Employee", employee, ["employee_name", "department"]
        ) or (None, None)

        if filters.get("department") and department != filters["department"]:
            continue

        retention = frappe.db.get_value(
            "Asset Retention Request",
            {"employee": employee, "asset": asset, "status": "Approved", "docstatus": ["!=", 2]},
            "name",
        )

        rows.append({
            "employee": employee,
            "employee_name": emp_name,
            "department": department,
            "asset": asset,
            "asset_name": latest.asset_name,
            "date": latest.transaction_date,
            "cost": cost,
            "retention_status": _("Yes ({0})").format(retention) if retention else "",
        })

    return rows
