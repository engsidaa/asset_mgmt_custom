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
            "label": "Purchase Date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "age_years",
            "label": "Age (Years)",
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "age_bucket",
            "label": "Age Bucket",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "gross_purchase_amount",
            "label": "Purchase Value",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "accumulated_depreciation_amount",
            "label": "Accumulated Depreciation",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "value_after_depreciation",
            "label": "Book Value",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "location",
            "label": "Location",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def _get_age_bucket(age_years):
    if age_years is None:
        return "Unknown"
    if age_years < 1:
        return "0-1 Year"
    elif age_years < 3:
        return "1-3 Years"
    elif age_years < 5:
        return "3-5 Years"
    elif age_years < 10:
        return "5-10 Years"
    else:
        return "10+ Years"


def get_data(filters):
    conditions = ""
    params = {}

    if filters.get("company"):
        conditions += " AND a.company = %(company)s"
        params["company"] = filters["company"]

    if filters.get("asset_category"):
        conditions += " AND a.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    rows = frappe.db.sql(
        """
        SELECT
            a.name AS asset,
            a.asset_name,
            a.asset_category,
            a.purchase_date,
            ROUND(DATEDIFF(CURDATE(), a.purchase_date) / 365.25, 1) AS age_years,
            a.gross_purchase_amount,
            a.accumulated_depreciation_amount,
            a.value_after_depreciation,
            a.status,
            a.location
        FROM `tabAsset` a
        WHERE a.docstatus < 2 AND a.status != 'Disposed of'
        {conditions}
        ORDER BY a.purchase_date ASC
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )

    selected_bucket = filters.get("age_bucket")

    data = []
    for row in rows:
        row.age_bucket = _get_age_bucket(row.age_years)
        if selected_bucket and selected_bucket != "All" and row.age_bucket != selected_bucket:
            continue
        data.append(row)

    return data
