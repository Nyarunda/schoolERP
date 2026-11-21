# Auto-link parent logins: acceptance

| # | Given / when | Then | Test | On test site |
|---|---|---|---|---|
| 1 | A parent login exists; a guardian with that email is added to a student and saved | Guardian row is linked; the parent's portal lists the child | `test_guardian_added_after_login` | [ ] |
| 2 | A guardian exists with phone 0712…; a parent login with mobile +254712… is created | Guardian row is linked without re-saving the student | `test_login_created_after_guardian` | [ ] |
| 3 | A staff (system) user has the guardian's email | Not linked | `test_staff_account_never_linked` | [ ] |
| 4 | Two parent logins match one guardian (one by email, one by phone) | Not linked; nothing changes | `test_ambiguous_match_left_alone` | [ ] |
| 5 | A guardian row already links a login | Kept as it is | `test_existing_link_kept` | [ ] |
| 6 | Phone written 0712 345 678 / 254712345678 / +254712345678 | All match | `test_logic.py::test_phone_variants` | — |

## Not broken

- [ ] `./scripts/check.sh` and CI green
- [ ] Give Parents Portal Access still links and creates logins
- [ ] School without the portal module: nothing linked

## Docs

- [ ] User guide section 7 (parents): links happen by themselves; the button is for new logins
- [ ] `CHANGELOG.md`
