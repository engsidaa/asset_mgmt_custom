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
        {"label": _("Total Budget"), "fieldname": "total_budget", "fieldtype": "Currency", "width": 140},
        {"label": _("Preventive Budget"), "fieldname": "preventive_budget", "fieldtype": "Currency", "width": 150},
        {"label": _("Corrective Budget"), "fieldname": "corrective_budget", "fieldtype": "Currency", "width": 150},
        {"label": _("AMC Budget"), "fieldname": "amc_budget", "fieldtype": "Currency", "width": 130},
        {"label": _("Actual Repair Cost"), "fieldname": "actual_repair", "fieldtype": "Currency", "width": 150},
        {"label": _("Actual AMC Cost"), "fieldname": "actual_amc", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Actual"), "fieldname": "total_actual", "fieldtype": "Currency", "width": 130},
        {"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 130},
        {"label": _("% Used"), "fieldname": "pct_used", "fieldtype": "Percent", "width": 100},
    ]


def get_data(filters):
    fy = filters.get("fiscal_year")
    branch_filter = filters.get("branch")
    company_filter = filters.get("company")

    # Get fiscal year date range
    fy_dates = frappe.db.get_value("Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True)
    if not fy_dates:
        return []

    # Fetch budgets
    budget_cond = "WHERE fiscal_year = %(fy)s"
    params = {"fy": fy, "from_date": fy_dates.year_start_date, "to_date": fy_dates.year_end_date}

    if branch_filter:
        budget_cond += " AND branch = %(branch)s"
        params["branch"] = branch_filter
    if company_filter:
        budget_cond += " AND company = %(company)s"
        params["company"] = company_filter

    budgets = frappe.db.sql(f"""
        SELECT branch, fiscal_year, total_budget, preventive_budget, corrective_budget, amc_budget
        FROM `tabAsset Maintenance Budget`
        {budget_cond}
        ORDER BY branch
    """, params, as_dict=True)

    if not budgets:
        return []

    branches = [b.branch for b in budgets]

    # Actual repair costs: sum from Asset Repair where asset's branch = branch
    repair_costs = frappe.db.sql("""
        SELECT a.custom_branch AS branch, SUM(ar.repair_cost) AS total
        FROM `tabAsset Repair` ar
        JOIN `tabAsset` a ON a.name = ar.asset
        WHERE ar.docstatus = 1
          AND a.custom_branch IN %(branches)s
          AND DATE(ar.failure_date) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY a.custom_branch
    """, dict(params, branches=branches), as_dict=True)
    repair_map = {r.branch: r.total or 0 for r in repair_costs}

    # Actual AMC costs: sum of contract_value from Asset Maintenance Contract where branch covered
    # ملاحظة: "Asset Maintenance Contract Item" مفهاش حقل custom_branch —
    # الفرع موجود على الأصل نفسه (Asset.custom_branch)، فلازم ننضم لجدول
    # الأصل عشان نوصله. النسخة القديمة كانت هتفشل بخطأ SQL خام.
    amc_costs = frappe.db.sql("""
        SELECT a.custom_branch AS branch, SUM(amc.contract_value) AS total
        FROM `tabAsset Maintenance Contract` amc
        JOIN `tabAsset Maintenance Contract Item` ami ON ami.parent = amc.name
        JOIN `tabAsset` a ON a.name = ami.asset
        WHERE amc.docstatus < 2
          AND amc.status != 'Expired'
          AND a.custom_branch IN %(branches)s
          AND amc.start_date <= %(to_date)s
          AND amc.end_date >= %(from_date)s
        GROUP BY a.custom_branch
    """, dict(params, branches=branches), as_dict=True)
    amc_map = {r.branch: r.total or 0 for r in amc_costs}

    rows = []
    for b in budgets:
        actual_repair = repair_map.get(b.branch, 0)
        actual_amc = amc_map.get(b.branch, 0)
        total_actual = actual_repair + actual_amc
        budget = b.total_budget or 0
        variance = budget - total_actual
        pct = round((total_actual / budget * 100), 1) if budget else 0

        rows.append({
            "branch": b.branch,
            "fiscal_year": b.fiscal_year,
            "total_budget": budget,
            "preventive_budget": b.preventive_budget or 0,
            "corrective_budget": b.corrective_budget or 0,
            "amc_budget": b.amc_budget or 0,
            "actual_repair": actual_repair,
            "actual_amc": actual_amc,
            "total_actual": total_actual,
            "variance": variance,
            "pct_used": pct,
        })

    return rows
