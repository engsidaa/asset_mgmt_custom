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
            "fieldname": "branch",
            "label": "Branch",
            "fieldtype": "Link",
            "options": "Branch",
            "width": 120,
        },
        {
            "fieldname": "asset_category",
            "label": "Asset Category",
            "fieldtype": "Link",
            "options": "Asset Category",
            "width": 140,
        },
        {
            "fieldname": "total_logs",
            "label": "Log Days",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "fieldname": "total_capacity_hours",
            "label": "Total Capacity Hrs",
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "fieldname": "total_used_hours",
            "label": "Total Used Hrs",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "fieldname": "total_idle_hours",
            "label": "Total Idle Hrs",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "fieldname": "total_downtime_hours",
            "label": "Total Downtime Hrs",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "fieldname": "avg_utilization_pct",
            "label": "Avg Utilization %",
            "fieldtype": "Float",
            "width": 130,
        },
    ]


def get_data(filters):
    conditions = ""
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("branch"):
        conditions += " AND u.branch = %(branch)s"
        params["branch"] = filters["branch"]

    if filters.get("asset_category"):
        conditions += (
            " AND (SELECT asset_category FROM `tabAsset`"
            " WHERE name = u.asset LIMIT 1) = %(asset_category)s"
        )
        params["asset_category"] = filters["asset_category"]

    return frappe.db.sql(
        """
        SELECT
            u.asset,
            MAX(u.asset_name) AS asset_name,
            MAX(u.branch) AS branch,
            (SELECT asset_category FROM `tabAsset` WHERE name = u.asset LIMIT 1) AS asset_category,
            COUNT(*) AS total_logs,
            SUM(u.total_capacity_hours) AS total_capacity_hours,
            SUM(u.actual_used_hours) AS total_used_hours,
            SUM(u.idle_hours) AS total_idle_hours,
            SUM(u.downtime_hours) AS total_downtime_hours,
            ROUND(AVG(u.utilization_pct), 1) AS avg_utilization_pct
        FROM `tabAsset Utilization Log` u
        WHERE u.log_date BETWEEN %(from_date)s AND %(to_date)s
        {conditions}
        GROUP BY u.asset
        ORDER BY avg_utilization_pct DESC
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )
