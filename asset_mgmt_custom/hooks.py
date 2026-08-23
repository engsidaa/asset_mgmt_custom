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
        "filters": [["dt", "in", ["Asset", "Asset Repair", "Location", "Asset Movement", "Asset Category"]]],
    },
    {
        "dt": "Workflow",
        "filters": [["document_type", "=", "Asset Movement"]],
    },
    {
        "dt": "Workflow State",
        "filters": [
            [
                "workflow_state_name",
                "in",
                ["Draft", "Pending Approval", "Approved", "Rejected"],
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
]

# ---------------------------------------------------------------------------
# Doc Events – هوكات server-side على doctypes موجودة في ERPNext
# ---------------------------------------------------------------------------
doc_events = {
    "Asset": {
        "validate": "asset_mgmt_custom.overrides.asset.validate",
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
}

# ---------------------------------------------------------------------------
# Scheduled Jobs
# ---------------------------------------------------------------------------
scheduler_events = {
    "daily": [
        "asset_mgmt_custom.tasks.send_incomplete_asset_alerts",
    ],
}
