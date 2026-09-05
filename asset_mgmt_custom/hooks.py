app_name = "asset_mgmt_custom"
app_title = "Asset Management Custom"
app_publisher = "Custom"
app_description = "Custom extensions for ERPNext Asset & Maintenance modules"
app_email = ""
app_license = "MIT"

# ---------------------------------------------------------------------------
# Fixtures – تُصدَّر وتُستورَد تلقائياً عند bench migrate
# ---------------------------------------------------------------------------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["dt", "in", ["Asset", "Asset Repair", "Location", "Asset Movement", "Asset Movement Item", "Asset Category", "Asset Category Account", "Asset Maintenance Contract", "Asset Maintenance", "Branch", "Maintenance Team Member"]]],
    },
    {
        "dt": "Property Setter",
        "filters": [["doc_type", "=", "Asset Repair"], ["field_name", "=", "downtime"]],
    },
    {
        "dt": "Custom DocPerm",
        "filters": [["role", "=", "Branch Manager"]],
    },
    {
        "dt": "Workflow",
        "filters": [["document_type", "in", ["Asset Movement", "Asset Retention Request"]]],
    },
    {
        "dt": "Workflow State",
        "filters": [
            [
                "workflow_state_name",
                "in",
                ["Draft", "Pending Approval", "Approved", "Rejected", "Fulfilled"],
            ]
        ],
    },
    {
        "dt": "Workflow Action Master",
        "filters": [
            [
                "workflow_action_name",
                "in",
                ["Submit for Approval", "Approve", "Reject", "Resubmit"],
            ]
        ],
    },
    {
        "dt": "Print Format",
        "filters": [["module", "=", "Asset Mgmt Custom"]],
    },
    {
        "dt": "Number Card",
        "filters": [["module", "=", "Asset Mgmt Custom"]],
    },
    {
        "dt": "Dashboard",
        "filters": [["module", "=", "Asset Mgmt Custom"]],
    },
    {
        "dt": "Workspace",
        "filters": [["module", "=", "Asset Mgmt Custom"]],
    },
]

# ---------------------------------------------------------------------------
# Doc Events – هوكات server-side على doctypes موجودة في ERPNext
# ---------------------------------------------------------------------------
doc_events = {
    "Asset": {
        "validate": "asset_mgmt_custom.overrides.asset.validate",
        "after_insert": "asset_mgmt_custom.overrides.asset.after_insert",
    },
    "Asset Movement": {
        "validate": "asset_mgmt_custom.overrides.asset_movement.validate",
        "on_submit": "asset_mgmt_custom.overrides.asset_movement.on_submit",
        "on_cancel": "asset_mgmt_custom.overrides.asset_movement.on_cancel",
    },
    "Asset Repair": {
        "validate": "asset_mgmt_custom.overrides.asset_repair.validate",
        "on_submit": "asset_mgmt_custom.overrides.asset_repair.on_submit",
        "on_cancel": "asset_mgmt_custom.overrides.asset_repair.on_cancel",
    },
    "Full and Final Statement": {
        "validate": "asset_mgmt_custom.overrides.full_and_final_statement.validate",
        "on_submit": "asset_mgmt_custom.overrides.full_and_final_statement.on_submit",
    },
    "Branch": {
        "on_update": "asset_mgmt_custom.overrides.branch.on_update",
    },
}

# ---------------------------------------------------------------------------
# Client Scripts – JavaScript يُضاف على الـ Form
# ---------------------------------------------------------------------------
doctype_js = {
    "Asset": "public/js/asset.js",
    "Asset Repair": "public/js/asset_repair.js",
    "Asset Movement": "public/js/asset_movement.js",
    "Asset Requisition": "public/js/asset_requisition.js",
    "Asset Loan": "asset_mgmt_custom/doctype/asset_loan/asset_loan.js",
    "Asset Disposal Request": "asset_mgmt_custom/doctype/asset_disposal_request/asset_disposal_request.js",
    "Asset Maintenance Contract": "asset_mgmt_custom/doctype/asset_maintenance_contract/asset_maintenance_contract.js",
    "Asset Physical Audit": "asset_mgmt_custom/doctype/asset_physical_audit/asset_physical_audit.js",
    "Asset Handover": "asset_mgmt_custom/doctype/asset_handover/asset_handover.js",
    "Asset Write Off Request": "asset_mgmt_custom/doctype/asset_write_off_request/asset_write_off_request.js",
}

# ---------------------------------------------------------------------------
# Scheduled Jobs
# ---------------------------------------------------------------------------
scheduler_events = {
    "daily": [
        "asset_mgmt_custom.tasks.send_incomplete_asset_alerts",
        "asset_mgmt_custom.tasks.send_maintenance_due_alerts",
        "asset_mgmt_custom.tasks.check_overdue_transit",
        "asset_mgmt_custom.tasks.check_requisition_sla",
        "asset_mgmt_custom.tasks.check_insurance_expiry",
        "asset_mgmt_custom.tasks.check_overdue_loans",
        "asset_mgmt_custom.tasks.check_amc_expiry",
        "asset_mgmt_custom.tasks.check_compliance_expiry",
        "asset_mgmt_custom.tasks.check_lease_expiry",
        "asset_mgmt_custom.tasks.check_overdue_checkouts",
        "asset_mgmt_custom.tasks.check_open_critical_incidents",
        "asset_mgmt_custom.tasks.check_missed_cleaning",
        "asset_mgmt_custom.tasks.check_spare_parts_low",
        "asset_mgmt_custom.tasks.check_permit_expiry",
        "asset_mgmt_custom.tasks.check_calibration_due",
        "asset_mgmt_custom.tasks.check_overdue_allocations",
        "asset_mgmt_custom.tasks.check_software_license_expiry",
        "asset_mgmt_custom.tasks.check_pm_schedule_due",
        "asset_mgmt_custom.tasks.check_overdue_bookings",
        "asset_mgmt_custom.tasks.check_expired_work_permits",
        "asset_mgmt_custom.tasks.check_overdue_work_orders",
    ],
    "weekly": [
        "asset_mgmt_custom.tasks.send_warranty_digest_email",
    ],
}

# ---------------------------------------------------------------------------
# Migration Hooks — run AFTER sync_fixtures(), unlike patches.txt entries
# ---------------------------------------------------------------------------
after_migrate = [
    "asset_mgmt_custom.setup.after_migrate.unify_asset_manager_role",
    "asset_mgmt_custom.setup.after_migrate.backfill_asset_coding_status",
    "asset_mgmt_custom.setup.after_migrate.remove_old_asset_requisition_workflow",
    "asset_mgmt_custom.setup.after_migrate.sync_branch_manager_user_permissions",
]
