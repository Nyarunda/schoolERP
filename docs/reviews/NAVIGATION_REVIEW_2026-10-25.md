# SchoolERP browser links and sidebar navigation review

## Confirmed source findings

- `school_erp/public/js/school_dashboard.js` sent `["Form", "Leave Application", "new"]` and similar routes through `frappe.set_route`. Frappe's supported new-document API is `frappe.new_doc(doctype)`; the shared route handler now uses it.
- Dashboard list navigation now explicitly clears old `frappe.route_options` for unfiltered lists. Previously a previously selected filter could persist into unrelated navigation.
- `Page` route arrays are now handled explicitly by navigating to the named Desk page.
- `school_erp/school/workspace/school/school.json` currently configures a single standard School workspace, with links grouped in Students, Fees, Staff, and Setup. This is not an independent role-specific sidebar implementation.
- The Management Dashboard and Staff Room are separate Desk pages. The Parent Portal uses the public website route `/parent`, so it is expected to have different navigation chrome from Desk.

## Recommended sidebar follow-up (not implemented in this patch)

1. Confirm exact browser URL, role, screenshot, and viewport size for each reported mismatch.
2. Define a canonical navigation inventory with actual Frappe DocType/Report/Page targets and authorize each by role.
3. Separate management, bursar, teaching, driver and parent navigation where appropriate without replacing Frappe's native routing.
4. Verify active-link highlighting, browser refresh, Back/Forward, collapsed desktop sidebar and mobile navigation.
5. Avoid duplicate menus; keep the standard School workspace discoverable as the app entry point.
6. Add navigation smoke tests for valid routes and permission-denied outcomes, across all supported roles.

## Validation required

- Build app assets: `bench build --app school_erp`.
- Clear cached site assets: `bench --site test.localhost clear-cache` and refresh the browser.
- Manually exercise Leave Application, Duty Report, the dashboards, Fee Balances and workspace navigation.
- This patch has not been run in a browser or on a live Frappe server.

This navigation adjustment belongs to the review branch and is not merged to main.
