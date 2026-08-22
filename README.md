# Asset Management Custom App

Custom Frappe app that extends ERPNext Asset & Maintenance modules.

## What This App Does

### Custom Fields Added

| Doctype | Field | Type | Purpose |
|---------|-------|------|---------|
| Asset | Sticker Code | Data | كود الستيكر الملصق على الأصل الفعلي |
| Asset | Asset Condition | Select (New/Used) | حالة الأصل |
| Asset | Used Depreciation Rate | Percent | نسبة إهلاك خاصة للأصول المستعملة |
| Location | Cost Center | Link | مركز التكلفة لكل فرع/موقع |
| Asset Repair | Labor Cost | Currency | تكلفة العمالة |
| Asset Repair | Technician Name | Data | اسم الفني |
| Asset Repair | Repair Notes | Long Text | ملاحظات الإصلاح |
| Asset Repair | Before Repair Image | Attach Image | صورة قبل الإصلاح |
| Asset Repair | After Repair Image | Attach Image | صورة بعد الإصلاح |

### Automated Behaviors

1. **Asset Condition = Used** → applies `custom_used_depreciation_rate` to all finance books automatically on save
2. **Asset Transfer** → updates `cost_center` on the asset to the target location's `custom_cost_center`
3. **Sticker code warning** → shows a yellow alert on Asset form until sticker code is assigned

### Workflow: Asset Movement Approval

```
Draft → [Submit for Approval] → Pending Approval → [Approve] → Approved (Submitted)
                                                  → [Reject]  → Rejected → [Resubmit] → Draft
```

## Installation

```bash
# From your bench directory
bench get-app https://github.com/<your-org>/asset_mgmt_custom
bench --site <your-site> install-app asset_mgmt_custom
bench --site <your-site> migrate
```

## After Installation

1. Go to **Location** and set the `Cost Center` on each branch/location
2. When creating an Asset, set `Asset Condition` (New/Used) and `Sticker Code`
3. Asset Movement now requires approval from **Assets Manager** role before submission
