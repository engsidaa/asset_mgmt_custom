import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"fieldname": "asset_name", "label": "Asset Name", "fieldtype": "Data", "width": 170},
        {"fieldname": "asset_category", "label": "Asset Category", "fieldtype": "Link", "options": "Asset Category", "width": 130},
        {"fieldname": "purchase_value", "label": "Purchase Value", "fieldtype": "Currency", "width": 120},
        {"fieldname": "total_maintenance_cost", "label": "Maintenance & Repair", "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_insurance_cost", "label": "Insurance", "fieldtype": "Currency", "width": 110},
        {"fieldname": "total_contract_cost", "label": "Vendor Contracts", "fieldtype": "Currency", "width": 130},
        {"fieldname": "total_lease_cost", "label": "Lease (to date)", "fieldtype": "Currency", "width": 120},
        {"fieldname": "total_software_cost", "label": "Software Licenses", "fieldtype": "Currency", "width": 130},
        {"fieldname": "total_spare_parts_cost", "label": "Spare Parts", "fieldtype": "Currency", "width": 110},
        {"fieldname": "total_writeoff_cost", "label": "Write-off Loss", "fieldtype": "Currency", "width": 120},
        {"fieldname": "total_energy_cost", "label": "Energy", "fieldtype": "Currency", "width": 100},
        {"fieldname": "total_fuel_cost", "label": "Fuel", "fieldtype": "Currency", "width": 100},
        {"fieldname": "tco", "label": "Total Cost of Ownership", "fieldtype": "Currency", "width": 150},
        {"fieldname": "age_years", "label": "Age (Yrs)", "fieldtype": "Float", "width": 85},
        {"fieldname": "annual_tco", "label": "Annual TCO", "fieldtype": "Currency", "width": 120},
    ]


def _sum_by_asset(query, params=None):
    return {r.asset: (r.cost or 0) for r in frappe.db.sql(query, params or {}, as_dict=True)}


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
            a.name AS asset,
            a.asset_name,
            a.asset_category,
            a.gross_purchase_amount AS purchase_value,
            IFNULL(a.custom_total_maintenance_cost, 0) AS total_maintenance_cost,
            ROUND(DATEDIFF(CURDATE(), a.purchase_date) / 365.25, 1) AS age_years
        FROM `tabAsset` a
        WHERE a.docstatus < 2 AND a.status != 'Disposed of'
        {asset_cond}
        """.format(asset_cond=asset_cond),
        params,
        as_dict=True,
    )

    # Insurance: sum of renewal premiums recorded against the asset.
    insurance_costs = _sum_by_asset(
        """
        SELECT asset, SUM(new_premium) AS cost
        FROM `tabAsset Insurance Renewal`
        WHERE docstatus = 1
        GROUP BY asset
        """
    )

    # Vendor contracts: a contract can cover several assets, so its value
    # is split evenly across every asset listed in its child table.
    contract_costs = _sum_by_asset(
        """
        SELECT ca.asset AS asset, SUM(c.contract_value / cnt.asset_count) AS cost
        FROM `tabAsset Vendor Contract Asset` ca
        JOIN `tabAsset Vendor Contract` c ON c.name = ca.parent
        JOIN (
            SELECT parent, COUNT(*) AS asset_count
            FROM `tabAsset Vendor Contract Asset`
            GROUP BY parent
        ) cnt ON cnt.parent = ca.parent
        WHERE c.docstatus = 1
        GROUP BY ca.asset
        """
    )

    # Lease: monthly rent accrued from start_date to end_date (or today if
    # the lease is still running).
    lease_costs = _sum_by_asset(
        """
        SELECT
            asset,
            SUM(
                monthly_rent * GREATEST(
                    TIMESTAMPDIFF(MONTH, start_date, LEAST(IFNULL(end_date, CURDATE()), CURDATE())),
                    0
                )
            ) AS cost
        FROM `tabAsset Lease`
        WHERE docstatus = 1 AND start_date IS NOT NULL
        GROUP BY asset
        """
    )

    software_costs = _sum_by_asset(
        """
        SELECT asset, SUM(annual_cost) AS cost
        FROM `tabAsset Software License`
        WHERE asset IS NOT NULL AND asset != ''
        GROUP BY asset
        """
    )

    # Spare parts actually issued against the asset (not just requested).
    spare_part_costs = _sum_by_asset(
        """
        SELECT r.asset AS asset, SUM(r.quantity_issued * IFNULL(sp.unit_cost, 0)) AS cost
        FROM `tabAsset Spare Part Request` r
        LEFT JOIN `tabAsset Spare Part` sp ON sp.name = r.spare_part
        WHERE r.status = 'Issued'
        GROUP BY r.asset
        """
    )

    writeoff_costs = _sum_by_asset(
        """
        SELECT asset, SUM(estimated_loss_value) AS cost
        FROM `tabAsset Write-off Request`
        WHERE docstatus = 1
        GROUP BY asset
        """
    )

    energy_costs = _sum_by_asset(
        """
        SELECT asset, SUM(total_cost) AS cost
        FROM `tabAsset Energy Log`
        GROUP BY asset
        """
    )

    fuel_costs = _sum_by_asset(
        """
        SELECT asset, SUM(total_cost) AS cost
        FROM `tabAsset Fuel Log`
        GROUP BY asset
        """
    )

    data = []
    for row in assets:
        row.total_insurance_cost = insurance_costs.get(row.asset, 0)
        row.total_contract_cost = contract_costs.get(row.asset, 0)
        row.total_lease_cost = lease_costs.get(row.asset, 0)
        row.total_software_cost = software_costs.get(row.asset, 0)
        row.total_spare_parts_cost = spare_part_costs.get(row.asset, 0)
        row.total_writeoff_cost = writeoff_costs.get(row.asset, 0)
        row.total_energy_cost = energy_costs.get(row.asset, 0)
        row.total_fuel_cost = fuel_costs.get(row.asset, 0)

        row.tco = (
            (row.purchase_value or 0)
            + row.total_maintenance_cost
            + row.total_insurance_cost
            + row.total_contract_cost
            + row.total_lease_cost
            + row.total_software_cost
            + row.total_spare_parts_cost
            + row.total_writeoff_cost
            + row.total_energy_cost
            + row.total_fuel_cost
        )
        age = row.age_years or 0
        row.annual_tco = round(row.tco / age, 2) if age > 0 else row.tco
        data.append(row)

    return sorted(data, key=lambda x: x.tco, reverse=True)
