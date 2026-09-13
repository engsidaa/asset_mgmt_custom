import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link",
         "options": "Asset", "width": 140},
        {"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 180},
        {"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Link",
         "options": "Asset Category", "width": 130},
        {"label": _("Branch / Cost Center"), "fieldname": "cost_center", "fieldtype": "Link",
         "options": "Cost Center", "width": 150},
        {"label": _("Reference Type"), "fieldname": "reference_doctype", "fieldtype": "Link",
         "options": "DocType", "width": 130},
        {"label": _("Reference No"), "fieldname": "reference_name", "fieldtype": "Dynamic Link",
         "options": "reference_doctype", "width": 130},
        {"label": _("Failure/Open Date"), "fieldname": "failure_date",
         "fieldtype": "Datetime", "width": 150},
        {"label": _("Completion Date"), "fieldname": "completion_date",
         "fieldtype": "Datetime", "width": 150},
        {"label": _("Downtime (hrs)"), "fieldname": "downtime_hours",
         "fieldtype": "Float", "precision": 2, "width": 110},
        {"label": _("Cost"), "fieldname": "cost",
         "fieldtype": "Currency", "width": 120},
        {"label": _("Status"), "fieldname": "status",
         "fieldtype": "Data", "width": 100},
    ]

    # المصدر وُسِّع ليشمل Asset Work Order (مش بس Asset Repair) — الغالبية
    # الساحقة من الصيانة التصحيحية الفعلية تمر عبر أمر العمل، وكانت مُغفَلة
    # بالكامل من تقرير التوقف هذا. صف واحد لكل مستند من المصدرين معاً.
    repair_conditions = "WHERE ar.docstatus = 1"
    wo_conditions = (
        "WHERE wo.docstatus = 1 AND wo.status = 'مكتمل' "
        "AND IFNULL(wo.is_preventive_maintenance, 0) = 0"
    )
    params = dict(filters)

    if filters.get("company"):
        repair_conditions += " AND a.company = %(company)s"
        wo_conditions += " AND a.company = %(company)s"
    if filters.get("from_date"):
        repair_conditions += " AND DATE(ar.failure_date) >= %(from_date)s"
        wo_conditions += " AND DATE(wo.creation) >= %(from_date)s"
    if filters.get("to_date"):
        repair_conditions += " AND DATE(ar.failure_date) <= %(to_date)s"
        wo_conditions += " AND DATE(wo.creation) <= %(to_date)s"
    if filters.get("cost_center"):
        repair_conditions += " AND a.cost_center = %(cost_center)s"
        wo_conditions += " AND a.cost_center = %(cost_center)s"
    if filters.get("asset_category"):
        repair_conditions += " AND a.asset_category = %(asset_category)s"
        wo_conditions += " AND a.asset_category = %(asset_category)s"

    data = frappe.db.sql(f"""
        SELECT
            ar.asset,
            a.asset_name,
            a.asset_category,
            a.cost_center,
            'Asset Repair'                               AS reference_doctype,
            ar.name                                      AS reference_name,
            ar.failure_date,
            ar.completion_date,
            IFNULL(ar.custom_downtime_hours, 0)          AS downtime_hours,
            ar.repair_cost                                AS cost,
            ar.repair_status                              AS status
        FROM `tabAsset Repair` ar
        JOIN `tabAsset` a ON a.name = ar.asset
        {repair_conditions}

        UNION ALL

        SELECT
            wo.asset,
            a.asset_name,
            a.asset_category,
            a.cost_center,
            'Asset Work Order'                            AS reference_doctype,
            wo.name                                       AS reference_name,
            wo.creation                                   AS failure_date,
            wo.closed_at                                  AS completion_date,
            IFNULL(wo.downtime_hours, 0)                  AS downtime_hours,
            IFNULL(NULLIF(wo.actual_cost, 0), IFNULL(wo.labor_cost, 0)) AS cost,
            wo.status                                     AS status
        FROM `tabAsset Work Order` wo
        JOIN `tabAsset` a ON a.name = wo.asset
        {wo_conditions}

        ORDER BY cost_center, asset, failure_date DESC
    """, params, as_dict=True)

    return columns, data
