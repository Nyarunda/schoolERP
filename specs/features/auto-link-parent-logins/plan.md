# Auto-link parent logins: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Link on Student save | Student `validate` | `api/portal.link_guardian_logins(student)`: fill `g.user` for empty rows |
| Link on login create/save | `doc_events["User"]` `after_insert` / `on_update` | `api/portal.link_login_to_guardians(user)`: `frappe.db.set_value` on matching guardian rows (no Student re-save) |
| Phone forms | — | `logic/text.phone_variants(raw, cc)`: the forms a phone may be stored in (pure, unit tested) |
| Parents only | User `user_type` | Only `Website User`, enabled; add Parent role if missing |

## Changes

| File | Change |
|---|---|
| `school_erp/logic/text.py` | `phone_variants()` |
| `school_erp/api/portal.py` | `parent_login_for(email, mobile, cc)`, `link_guardian_logins(doc)`, `link_login_to_guardians(doc)` |
| `school_erp/school/doctype/student/student.py` | `validate` calls `link_guardian_logins(self)` |
| `school_erp/hooks.py` | User `after_insert` + `on_update` → `link_login_to_guardians` |
| `school_erp/tests/test_logic.py` | `phone_variants` unit tests |
| `school_erp/tests/test_parent_login_link.py` | Integration: both orders, staff never linked, ambiguity, idempotent |

## Data and migration

None. Existing unlinked rows get linked the next time the student or the login is saved (or by the button).

## Risks

- Linking a staff account to a student: prevented by `user_type == "Website User"`.
- Hook cost on every User save: one indexed query on `tabStudent Guardian` by email/mobile; skipped for system users.

## Deploy notes

No JS. `migrate` + `clear-cache` + restart; no backup needed.
