# SchoolERP navigation review — corrected after Frappe 16.52 browser testing

## Outcome

The navigation change in commit `2559462` is a **non-urgent cleanup**, not a confirmed defect fix. Independent browser testing reported no behavioral difference for dashboard routes in Frappe 16.52. This note supersedes the earlier source-only claims in this document.

## Findings from browser validation (reported by reviewer)

| Earlier claim | Browser finding |
| --- | --- |
| `frappe.set_route("Form", X, "new")` fails | Not reproduced. Both the old route and `frappe.new_doc(X)` open a new unsaved form. |
| Existing list filters leak into unfiltered lists | Not reproduced in the tested navigation sequences. |
| New `Page` route handling fixes a path | No current dashboard calls this route form; no user-visible effect. |
| Missing document name in `Form` route previously opened a list | Behavioral change is real but not reachable through the tested dashboard UI. |

These are reviewer-reported observations, not independent browser tests executed by this assistant.

## Sidebar architecture correction

The previous document inaccurately described the app as having only one School workspace. The reviewer confirms **six workspaces and a separate sidebar definition**. The old analysis inspected `main` rather than the separate `ui-refresh-dashboards` branch, which contains newer dashboard work. Review that branch before making additional sidebar recommendations. Avoid assuming the School workspace is the entire navigation system.

## Decision

- Keep `2559462` as optional code cleanup; do not represent it as a required navigation fix.
- Prioritize reproducible browser failures over speculative routing problems.
- No urgent navigation patch is justified from this comparison alone.
- When merging `ui-refresh-dashboards` and this PR, verify the combined navigation and styles at the resulting commit. The reviewer reports the UI branch does not modify `school_dashboard.js`; still confirm in the final merge diff.

## Follow-up test matrix (not implemented here)

1. Verify URLs and active sidebar state in every workspace and for each role.
2. Check navigation from dashboard links, workspace entries, direct URLs and browser Back/Forward.
3. Test narrow screens, collapsed sidebars and dark mode.
4. Ensure no permission-denied or not-found links are displayed to users lacking access.
5. Confirm new dashboard code from `ui-refresh-dashboards` before documenting its final sidebar behavior.

No runtime test was executed as part of this documentation correction. The reviewer reports that browser tests created only unsaved forms and made no saved changes.
