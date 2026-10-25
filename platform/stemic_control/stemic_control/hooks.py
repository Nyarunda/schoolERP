app_name = "stemic_control"
app_title = "Stemic Schools Admin"
app_publisher = "Stemic"
app_description = "Separate multi-tenant SaaS control plane for Stemic Schools"
app_email = "support@stemischools.com"
app_license = "mit"

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
app_include_css = ["/assets/stemic_control/css/stemic_overview.css"]
