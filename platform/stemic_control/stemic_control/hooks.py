app_name = "stemic_control"
app_title = "Stemic Schools Admin"
app_publisher = "Stemic"
app_description = "Separate multi-tenant SaaS control plane for Stemic Schools"
app_email = "support@stemischools.com"
app_license = "mit"

# Install only on admin.stemischools.com, never on school tenant sites.
after_install = "stemic_control.setup.install"
