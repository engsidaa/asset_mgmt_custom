app_name = "asset_mgmt_custom"
app_title = "Asset Management Custom"
app_publisher = "Custom"
app_description = "Custom extensions for ERPNext Asset & Maintenance modules"
app_email = ""
app_license = "MIT"

# ---------------------------------------------------------------------------
# Fixtures – تُصدَّر/تُستورَد تلقائياً عند bench migrate
# ---------------------------------------------------------------------------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["dt", "in", ["Asset", "Asset Repair", "Location"]]],
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
                ["Submit for Approval", "Approve", "Reject"],
            ]
        ],
    },
]

# ---------------------------------------------------------------------------
# Doc Events – هوكات على doctypes موجودة في ERPNext
# ---------------------------------------------------------------------------
doc_events = {
    "Asset Movement": {
        "on_submit": "asset_mgmt_custom.overrides.asset_movement.on_submit",
        "on_cancel": "asset_mgmt_custom.overrides.asset_movement.on_cancel",
    },
    "Asset": {
        "validate": "asset_mgmt_custom.overrides.asset.validate",
    },
}

# ---------------------------------------------------------------------------
# Client Scripts – JavaScript مُدرج على الـ Form
# ---------------------------------------------------------------------------
doctype_js = {
    "Asset": "public/js/asset.js",
    "Asset Repair": "public/js/asset_repair.js",
}
