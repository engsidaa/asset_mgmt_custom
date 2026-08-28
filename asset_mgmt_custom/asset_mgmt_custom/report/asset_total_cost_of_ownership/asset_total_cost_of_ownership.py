import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "asset",
            "label": "Asset",
            "fieldtype": "Link",
            "options": "Asset",
            "width": 150,
        },
        {
            "fieldname": "asset_name",
            "label": "Asset Name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "asset_category",
            "label": "Asset Category",
            "fieldtype": "Link",
            "options": "Asset Category",
            "width": 140,
        },
        {
            "fieldname": "purchase_value",
            "label": "Purchase Value",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "total_repair_cost",
            "label": "Repair Costs",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "total_maintenance_cost",
            "label": "Maintenance Costs",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "total_insurance_cost",
            "label": "Insurance Costs",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "total_energy_cost",
            "label": "Energy Costs",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "total_fuel_cost",
            "label": "Fuel Costs",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "tco",
            "label": "Total Cost of Ownership",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "age_years",
            "label": "Age (Yrs)",
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "annual_tco",
            "label": "Annual TCO",
            "fieldtype": "Currency",
            "width": 130,
        },
    ]


def get_data(filters):
    params = {}
    asset_cond = ""

    if filters.get("asset_category"):
        asset_cond += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        asset_cond += " AND a.company = %(company)s"
        params["company"] = filters["company"]

    assets = frappe.db.sql(
        """
        SELECT
            name AS asset,
            asset_name,
            asset_category,
            gross_purchase_amount AS purchase_value,
            ROUND(DATEDIFF(CURDATE(), purchase_date) / 365.25, 1) AS age_years
        FROM `tabAsset`
        WHERE docstatus < 2 AND status != 'Disposed of'
        {asset_cond}
        """.format(asset_cond=asset_cond),
        params,
        as_dict=True,
    )

    repair_costs = {
        r.asset: r.cost
        for r in frappe.db.sql(
            """
            SELECT asset, SUM(repair_cost) AS cost
            FROM `tabAsset Repair`
            WHERE docstatus = 1
            GROUP BY asset
            """,
            as_dict=True,
        )
    }

    energy_costs = {
        r.asset: r.cost
        for r in frappe.db.sql(
            """
            SELECT asset, SUM(total_cost) AS cost
            FROM `tabAsset Energy Log`
            GROUP BY asset
            """,
            as_dict=True,
        )
    }

    fuel_costs = {
        r.asset: r.cost
        for r in frappe.db.sql(
            """
            SELECT asset, SUM(total_cost) AS cost
            FROM `tabAsset Fuel Log`
            GROUP BY asset
            """,
            as_dict=True,
        )
    }

    data = []
    for row in assets:
        row.total_repair_cost = repair_costs.get(row.asset, 0) or 0
        row.total_maintenance_cost = 0
        row.total_insurance_cost = 0
        row.total_energy_cost = energy_costs.get(row.asset, 0) or 0
        row.total_fuel_cost = fuel_costs.get(row.asset, 0) or 0
        row.tco = (
            (row.purchase_value or 0)
            + row.total_repair_cost
            + row.total_energy_cost
            + row.total_fuel_cost
        )
        age = row.age_years or 0
        row.annual_tco = round(row.tco / age, 2) if age > 0 else row.tco
        data.append(row)

    return sorted(data, key=lambda x: x.tco, reverse=True)
