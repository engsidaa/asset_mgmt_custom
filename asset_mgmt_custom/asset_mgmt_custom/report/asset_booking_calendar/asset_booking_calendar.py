import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "booking",
            "label": "Booking",
            "fieldtype": "Link",
            "options": "Asset Booking",
            "width": 140,
        },
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
            "width": 170,
        },
        {
            "fieldname": "booked_by",
            "label": "Booked By",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {
            "fieldname": "department",
            "label": "Department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 130,
        },
        {
            "fieldname": "from_datetime",
            "label": "From",
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "fieldname": "to_datetime",
            "label": "To",
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "fieldname": "duration_hours",
            "label": "Duration (Hrs)",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "fieldname": "purpose",
            "label": "Purpose",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Data",
            "width": 100,
        },
    ]


def get_data(filters):
    conditions = ""
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("asset"):
        conditions += " AND b.asset = %(asset)s"
        params["asset"] = filters["asset"]

    if filters.get("asset_category"):
        conditions += (
            " AND (SELECT asset_category FROM `tabAsset`"
            " WHERE name = b.asset LIMIT 1) = %(asset_category)s"
        )
        params["asset_category"] = filters["asset_category"]

    if filters.get("status"):
        conditions += " AND b.status = %(status)s"
        params["status"] = filters["status"]

    return frappe.db.sql(
        """
        SELECT
            b.name AS booking,
            b.asset,
            b.asset_name,
            b.booked_by,
            b.department,
            b.from_datetime,
            b.to_datetime,
            ROUND(TIMESTAMPDIFF(MINUTE, b.from_datetime, b.to_datetime) / 60, 1) AS duration_hours,
            b.purpose,
            b.status
        FROM `tabAsset Booking` b
        WHERE b.docstatus < 2
          AND DATE(b.from_datetime) BETWEEN %(from_date)s AND %(to_date)s
        {conditions}
        ORDER BY b.from_datetime ASC
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )
