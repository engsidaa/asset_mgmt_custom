import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 160},
        {"label": _("Fiscal Year"), "fieldname": "fiscal_year", "fieldtype": "Data", "width": 100},
        {"label": _("Total CapEx Budget"), "fieldname": "total_budget", "fieldtype": "Currency", "width": 150},
        {"label": _("New Acquisition Budget"), "fieldname": "new_acquisition_budget", "fieldtype": "Currency", "width": 170},
        {"label": _("Replacement Budget"), "fieldname": "replacement_budget", "fieldtype": "Currency", "width": 150},
        {"label": _("Upgrade Budget"), "fieldname": "upgrade_budget", "fieldtype": "Currency", "width": 140},
        {"label": _("Actual Acquisition Cost"), "fieldname": "actual_acquisition", "fieldtype": "Currency", "width": 170},
        {"label": _("Total Actual"), "fieldname": "total_actual", "fieldtype": "Currency", "width": 130},
        {"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 130},
        {"label": _("% Used"), "fieldname": "pct_used", "fieldtype": "Percent", "width": 100},
    ]


def get_data(filters):
    fy = filters.get("fiscal_year")
    branch_filter = filters.get("branch")
    company_filter = filters.get("company")

    fy_dates = frappe.db.get_value(
        "Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True
    )
    if not fy_dates:
        return []

    params = {
        "fy": fy,
        "from_date": fy_dates.year_start_date,
        "to_date": fy_dates.year_end_date,
    }

    budget_cond = "WHERE fiscal_year = %(fy)s AND docstatus = 1"
    if branch_filter:
        budget_cond += " AND branch = %(branch)s"
        params["branch"] = branch_filter
    if company_filter:
        budget_cond += " AND company = %(company)s"
        params["company"] = company_filter

    budgets = frappe.db.sql(f"""
        SELECT branch, fiscal_year, total_capex_budget, new_acquisition_budget,
               replacement_budget, upgrade_budget
        FROM `tabAsset CapEx Budget`
        {budget_cond}
        ORDER BY branch
    """, params, as_dict=True)

    if not budgets:
        return []

    branches = [b.branch for b in budgets]

    # Actual cost = gross_purchase_amount of assets purchased in fiscal year per branch
    actuals = frappe.db.sql("""
        SELECT custom_branch AS branch, SUM(gross_purchase_amount) AS total
        FROM `tabAsset`
        WHERE docstatus = 1
          AND custom_branch IN %(branches)s
          AND purchase_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY custom_branch
    """, dict(params, branches=branches), as_dict=True)
    actual_map = {r.branch: r.total or 0 for r in actuals}

    rows = []
    for b in budgets:
        total_budget = b.total_capex_budget or 0
        actual = actual_map.get(b.branch, 0)
        variance = total_budget - actual
        pct = round((actual / total_budget * 100), 1) if total_budget else 0
        rows.append({
            "branch": b.branch,
            "fiscal_year": b.fiscal_year,
            "total_budget": total_budget,
            "new_acquisition_budget": b.new_acquisition_budget or 0,
            "replacement_budget": b.replacement_budget or 0,
            "upgrade_budget": b.upgrade_budget or 0,
            "actual_acquisition": actual,
            "total_actual": actual,
            "variance": variance,
            "pct_used": pct,
        })

    return rows
