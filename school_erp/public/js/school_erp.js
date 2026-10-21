// Global: license banner for admins
$(document).on("app_ready", () => {
	const lic = frappe.boot.school_erp;
	if (!lic || !frappe.user.has_role(["System Manager", "School Admin"])) return;
	const warn = ["grace", "expired", "invalid"].includes(lic.status) || (lic.days_left !== null && lic.days_left <= 30);
	if (warn) {
		frappe.show_alert({ message: __(lic.message), indicator: lic.status === "valid" ? "orange" : "red" }, 12);
	}
});
