import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "branch", "label": "الفرع", "fieldtype": "Link", "options": "Branch", "width": 150},
        {"fieldname": "electricity_co2e_kg", "label": "الكهرباء (كجم CO2e)", "fieldtype": "Float", "width": 150},
        {"fieldname": "fuel_co2e_kg", "label": "الوقود (كجم CO2e)", "fieldtype": "Float", "width": 150},
        {"fieldname": "total_co2e_kg", "label": "الإجمالي (كجم CO2e)", "fieldtype": "Float", "width": 150},
        {"fieldname": "anomaly_count", "label": "حالات شذوذ استهلاك", "fieldtype": "Int", "width": 130},
    ]


def get_data(filters):
    # Asset Fuel Log.log_date حقل Date حقيقي، فيدعم فلترة زمنية فعلية.
    # Asset Energy Log.log_month حقل نصي حر (Data) وليس Date — لا يوجد
    # فلتر زمني موثوق ممكن عليه، فأرقامه هنا دائماً تراكمية لكل السجلات.
    fuel_cond = ""
    fuel_params = {}
    if filters.get("from_date"):
        fuel_cond += " AND log_date >= %(from_date)s"
        fuel_params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        fuel_cond += " AND log_date <= %(to_date)s"
        fuel_params["to_date"] = filters["to_date"]

    electricity = {
        r.branch: r.total for r in frappe.db.sql(
            """
            SELECT branch, SUM(IFNULL(co2e_kg, 0)) AS total
            FROM `tabAsset Energy Log`
            WHERE branch IS NOT NULL AND branch != ''
            GROUP BY branch
            """, as_dict=True,
        )
    }
    electricity_anomalies = {
        r.branch: r.cnt for r in frappe.db.sql(
            """
            SELECT branch, COUNT(*) AS cnt
            FROM `tabAsset Energy Log`
            WHERE IFNULL(is_anomaly, 0) = 1 AND branch IS NOT NULL AND branch != ''
            GROUP BY branch
            """, as_dict=True,
        )
    }

    fuel = {
        r.branch: r.total for r in frappe.db.sql(
            f"""
            SELECT branch, SUM(IFNULL(co2e_kg, 0)) AS total
            FROM `tabAsset Fuel Log`
            WHERE branch IS NOT NULL AND branch != '' {fuel_cond}
            GROUP BY branch
            """, fuel_params, as_dict=True,
        )
    }
    fuel_anomalies = {
        r.branch: r.cnt for r in frappe.db.sql(
            f"""
            SELECT branch, COUNT(*) AS cnt
            FROM `tabAsset Fuel Log`
            WHERE IFNULL(is_anomaly, 0) = 1 AND branch IS NOT NULL AND branch != '' {fuel_cond}
            GROUP BY branch
            """, fuel_params, as_dict=True,
        )
    }

    branches = set(electricity) | set(fuel)
    data = []
    for branch in branches:
        elec = electricity.get(branch, 0) or 0
        fue = fuel.get(branch, 0) or 0
        data.append({
            "branch": branch,
            "electricity_co2e_kg": round(elec, 1),
            "fuel_co2e_kg": round(fue, 1),
            "total_co2e_kg": round(elec + fue, 1),
            "anomaly_count": (electricity_anomalies.get(branch, 0) or 0) + (fuel_anomalies.get(branch, 0) or 0),
        })

    return sorted(data, key=lambda r: r["total_co2e_kg"], reverse=True)
