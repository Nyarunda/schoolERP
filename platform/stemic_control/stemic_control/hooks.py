app_name = "stemic_control"
app_title = "Stemic Schools Admin"
app_publisher = "Stemic"
app_description = "Separate multi-tenant SaaS control plane for Stemic Schools"
app_email = "support@stemischools.com"
app_license = "mit"

add_to_apps_screen = [
    {
        "name": "stemic_control",
        "logo": "/assets/stemic_control/images/stemic.svg",
        "title": "Stemic Control",
        "route": "/desk/stemic-control",
        "has_permission": "stemic_control.permissions.has_app_permission",
    }
]

# Install only on admin.stemischools.com, never on school tenant sites.
after_install = "stemic_control.setup.install"

# Agents only see the schools and subscriptions they brought in
permission_query_conditions = {
    "SaaS Tenant": "stemic_control.permissions.tenant_query",
    "SaaS Subscription": "stemic_control.permissions.subscription_query",
    "SaaS Agent": "stemic_control.permissions.agent_query",
}
has_permission = {
    "SaaS Tenant": "stemic_control.permissions.tenant_has_permission",
    "SaaS Subscription": "stemic_control.permissions.subscription_has_permission",
    "SaaS Agent": "stemic_control.permissions.agent_has_permission",
}

# Admin KPI page only; keep the school tenant app unaffected.
app_include_js = ["stemic_control.bundle.js"]
app_include_css = ["stemic_overview.bundle.css"]  # bundled: hashed file name, so browsers pick up changes

# Local provisioner safety net: picks up queued jobs and fails abandoned ones (only when switched on)
scheduler_events = {"cron": {"*/5 * * * *": ["stemic_control.provisioner.process_queue"]}}

# Finance operators review tax records through controlled service actions.
doctype_js = {"SaaS eTIMS Invoice": "public/js/etims_invoice.js"}
