import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "budget",
            "label": "Budget",
            "fieldtype": "Link",
            "options": "Asset CapEx Budget",
            "width": 160,
        },
        {
            "fieldname": "asset_category",
            "label": "Asset Category",
            "fieldtype": "Link",
            "options": "Asset Category",
            "width": 150,
        },
        {
            "fieldname": "fiscal_year",
            "label": "Fiscal Year",
            "fieldtype": "Link",
            "options": "Fiscal Year",
            "width": 110,
        },
        {
            "fieldname": "total_capex_budget",
            "label": "Total Budget",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "new_acquisition_budget",
            "label": "Acquisition Budget",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "fieldname": "replacement_budget",
            "label": "Replacement Budget",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "upgrade_budget",
            "label": "Upgrade Budget",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "actual_spent",
            "label": "Actual Spent",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "variance",
            "label": "Variance",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "variance_pct",
            "label": "Variance %",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Data",
            "width": 100,
        },
    ]


def get_data(filters):
    # ملاحظة: "Asset CapEx Budget" نفسها لا تحمل حقل asset_category —
    # الفئة موجودة فقط في جدولها الفرعي "items" (Asset CapEx Budget Item)،
    # لأن ميزانية واحدة ممكن تغطي أكتر من فئة أصل. النسخة السابقة من هذا
    # التقرير كانت بتستعلم b.asset_category على الجدول الأب مباشرة — عمود
    # غير موجود، وكانت هتفشل بخطأ SQL خام أول ما حد يفتح التقرير. الحل هنا:
    # ننضم للجدول الفرعي، وناخد total_cost بتاع كل صف فئة كميزانيتها
    # (بدل تكرار الميزانية الإجمالية لكل المستند على كل فئة).
    conditions = ""
    params = {}

    if filters.get("fiscal_year"):
        conditions += " AND b.fiscal_year = %(fiscal_year)s"
        params["fiscal_year"] = filters["fiscal_year"]

    if filters.get("asset_category"):
        conditions += " AND i.asset_category = %(asset_category)s"
        params["asset_category"] = filters["asset_category"]

    if filters.get("company"):
        conditions += " AND b.company = %(company)s"
        params["company"] = filters["company"]

    rows = frappe.db.sql(
        """
        SELECT
            b.name AS budget,
            i.asset_category,
            b.fiscal_year,
            i.total_cost AS total_capex_budget,
            b.new_acquisition_budget,
            b.replacement_budget,
            b.upgrade_budget,
            COALESCE((
                SELECT SUM(gross_purchase_amount)
                FROM `tabAsset`
                WHERE asset_category = i.asset_category
                  AND docstatus = 1
                  AND YEAR(purchase_date) = (
                      SELECT YEAR(year_start_date)
                      FROM `tabFiscal Year`
                      WHERE name = b.fiscal_year
                      LIMIT 1
                  )
            ), 0) AS actual_spent,
            b.status
        FROM `tabAsset CapEx Budget` b
        JOIN `tabAsset CapEx Budget Item` i ON i.parent = b.name
        WHERE b.docstatus = 1
        {conditions}
        ORDER BY b.fiscal_year DESC, i.asset_category
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )

    for row in rows:
        budget = row.total_capex_budget or 0
        actual = row.actual_spent or 0
        row.variance = budget - actual
        row.variance_pct = round((row.variance / budget * 100), 2) if budget else 0.0

    return rows
