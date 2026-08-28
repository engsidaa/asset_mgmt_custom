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
            "fieldname": "purchase_date",
            "label": "Acquired",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "expected_end_of_life",
            "label": "Expected EOL",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "age_years",
            "label": "Age (Years)",
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "lifecycle_stage",
            "label": "Lifecycle Stage",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "total_repairs",
            "label": "Total Repairs",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "last_repair_date",
            "label": "Last Repair Date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "condition",
            "label": "Last Condition",
            "fieldtype": "Data",
            "width": 110,
        },
    ]


def _get_lifecycle_stage(status, age_years):
    if status == "Disposed of":
        return "Disposed"
    age = age_years or 0
    if age < 2:
        return "New"
    elif age < 5:
        return "Active"
    elif age <= 10:
        return "Mature"
    else:
        return "End of Life"


def get_data(filters):
    conditions = ""
    params = {}

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        params["company"] = filters["company"]

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    if filters.get("status"):
        conditions += " AND a.status = %(status)s"
        params["status"] = filters["status"]

    rows = frappe.db.sql(
        """
        SELECT
            a.name AS asset,
            a.asset_name,
            a.asset_category,
            a.purchase_date,
            a.disposal_date AS expected_end_of_life,
            ROUND(DATEDIFF(CURDATE(), a.purchase_date) / 365.25, 1) AS age_years,
            a.status,
            (SELECT COUNT(*) FROM `tabAsset Repair`
             WHERE asset = a.name AND docstatus = 1) AS total_repairs,
            (SELECT MAX(failure_date) FROM `tabAsset Repair`
             WHERE asset = a.name AND docstatus = 1) AS last_repair_date,
            (SELECT overall_condition FROM `tabAsset Condition Assessment`
             WHERE asset = a.name ORDER BY assessment_date DESC LIMIT 1) AS condition
        FROM `tabAsset` a
        WHERE a.docstatus < 2
        {conditions}
        ORDER BY a.purchase_date ASC
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )

    for row in rows:
        row.lifecycle_stage = _get_lifecycle_stage(row.status, row.age_years)

    return rows
