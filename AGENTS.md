# AGENTS.md: rules for anyone (person or agent) changing this repo

Read this first, then `specs/brief.md`, `specs/tech-design.md` and `specs/roadmap.md`. Every piece of work starts from
those files, not from memory or the chat.

## What this project is

**schoolERP** (`school_erp`) is a school management app on Frappe v16 / ERPNext v16 for Kenyan private schools, sold as
a hosted service by Stemic Technologies. **Stemic Control** (`platform/stemic_control`) is the separate control-plane
app on `admin.stemicschools.com`: schools, plans, subscriptions, licences, domains, provisioning.

| Site | What it is | Care |
|---|---|---|
| `admin.stemicschools.com` | Control Center (stemic_control) | Platform data; never install school_erp here |
| `test.stemicschools.com` | Stemic Test School: test everything here first | Safe for test records (prefix them `TEST`) |
| `<school>.stemicschools.com` | Live schools (e.g. mogongapagsecondary) | Real learners and money: no tests, no new modules until tested |

## How we work: spec-driven development

Every feature follows the same loop, on its own branch, as **one pull request**:

1. **Spec**: `specs/features/<slug>/requirements.md`, `plan.md`, `acceptance.md` (copy `specs/features/_template/`).
   Add the feature to `specs/roadmap.md` as *In progress*. Ask the owner only what changes what gets built.
2. **Implement** from the plan. Business rules go in `school_erp/logic/` (pure Python, unit tested); Frappe glue in
   `api/`; DocTypes in `school/doctype/`.
3. **Test**: `./scripts/check.sh` locally, then CI (Quick checks + Integration tests on Frappe/ERPNext v16) must be
   green. After deploy, verify the acceptance list on `test.stemicschools.com`.
4. **Docs**: README module table if a module changed, `docs/<TOPIC>.md` for anything a school admin needs, the user
   guide (Claude Docs "Stemic School ERP user guide"), and `CHANGELOG.md`.
5. **Finalise**: the owner says "merge" → squash-merge, mark the roadmap item *Done* with the PR number, give the
   deploy commands, replan if something shifted.

Small fixes found on the way may ride in the same PR when they are about the same feature; otherwise a separate
`fix/` PR. Never merge without the owner's go-ahead in chat.

## Code rules (learned the hard way)

- **Licensing**: module codes live in `school_erp/logic/license.py` (`MODULES`, `DOCTYPE_MODULE`, `READABLE_WITH`) and
  are mirrored in `platform/stemic_control/stemic_control/policy.py`; a test keeps them in sync. Module help text is in
  `school_settings.js` and `stemic_control.bundle.js`. Gate code with `licensing.require("<module>")`.
- **School Viewer** must be able to read every School DocType and report (`tests/test_viewer.py`).
- **Settings singles**: read them through `api/singles.py get_settings(doctype)` so JSON defaults apply on new sites.
- **Sidebar** (`school_erp/school/sidebar/school/school.json`): when you change it, bump its `"modified"`, or
  `bench migrate` skips the file (check.sh enforces this).
- **Frappe pitfalls**: `frappe.enqueue` reserves `event`, `queue`, `timeout`, `now`... as kwargs (use `kind`);
  validate in `before_submit`/`before_cancel`, not `on_*`; the bench test runner imports every `tests/test_*.py`, so
  never `import pytest` in a bench test; read `frappe.get_roles()` rather than trusting a role name in the client.
- **Role profiles** reset a user's roles on save; roles earned from records are put back by
  `setup/role_profiles.keep_derived_roles`. Add new earned roles there.
- **Caches**: anything that changes what the desk shows (licence, roles) must clear the boot cache
  (`frappe.cache.delete_key("bootinfo")`).
- **Merges**: after merging main into a branch, re-check `api/portal.py`, `scripts/check.sh` and the sidebar JSON; union
  merges have silently dropped lines there before.
- **Money and SMS**: never send real SMS or move money in tests; the test site has no SMS gateway on purpose.
- **Secrets**: no keys, passwords or tokens in the repo, chat or docs. `vendor.key` never leaves the owner's machine.

## Testing

- `./scripts/check.sh`: compile, DocType validation, JS syntax, unit tests, sidebar and key guards. Add new pure
  `logic/` test files to its pytest list.
- Integration tests: `bench --site test.localhost run-tests --app school_erp` (CI runs them on every PR). Model new
  ones on `tests/test_report_cards_per_stream.py`: `setup_school(cls)`, unique names, `cls._pub.stop()` in teardown.
- Acceptance on the test site is done in the browser as the school admin; never type passwords for anyone.

## Deploy (owner runs on `frappe@stemic-prod`)

```bash
cd ~/frappe-bench/apps/school_erp && git pull upstream main
cd ~/frappe-bench && bench --site all backup --with-files      # skip for doc/sidebar-only changes
bench --site all migrate
bench build --app school_erp                                     # only when JS/CSS changed
bench --site all clear-cache
sudo supervisorctl restart all
```

The server's remote is `upstream`, not `origin`.

## Writing for schools

Plain English for head teachers and bursars: short sentences, the button names in **bold**, Kenyan context (KES,
M-Pesa, CBC, NEMIS, terms). No jargon in user-facing text, docs or SMS templates.
