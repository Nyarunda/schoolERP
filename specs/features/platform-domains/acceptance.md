# Several platform domains: acceptance

| # | Given / when | Then | Test | On test site (admin) |
|---|---|---|---|---|
| 1 | No domain list | stemicschools.com is the default and only domain; nothing changes | `test_no_list_keeps_single_domain` | [x] |
| 2 | List with stemicschools.com (default) and stemic.cloud | Both offered, default first; two defaults or a bad name refused | `test_list_and_default`, `test_settings_validation` | [ ] |
| 3 | Onboard with stemic.cloud | `<slug>.stemic.cloud` claimed and verified at once; tenant remembers stemic.cloud | `test_onboard_on_second_domain` | [ ] |
| 4 | Address taken / reserved on the chosen domain | Refused | `test_slug_check_per_domain` | [ ] |
| 5 | Claim `<slug>.other-known-domain` for a school | Verified without TXT; another school's slug refused | `test_request_domain_any_known` | — |
| 6 | School on stemic.cloud has a site | Its address is routed; when the live check passes it becomes Active and primary | `test_routed_and_made_primary` | [ ] |
| 7 | Disable stemic.cloud | Not offered; its schools still routed | `test_disabled_domain_still_routes` | [ ] |
| 8 | Check Domains | Per domain: DNS and certificate state in words | `test_health_states` | [x] |
| 9 | Migrate | Existing schools get `platform_domain` = current default | `test_patch_backfills` | [x] |

## Not broken

- [x] CI green (all Control Center tests, incl. wizard, domains, provisioner)
- [ ] Custom domains still need TXT
- [x] Existing schools' addresses and links unchanged

## Docs

- [ ] `platform/stemic_control/README.md` and `server/README.md`: adding a platform domain
- [ ] `CHANGELOG.md`
