# School website: acceptance

*Each line is checked twice: by automated tests in CI, and by hand on test.stemicschools.com after deploy. The
feature is Done when every box is ticked.*

| # | Given / when | Then | Test | On test site |
|---|---|---|---|---|
| 1 | A guest opens "/" | The school homepage shows the school name, the crest (logo or initials) and the action cards. It is not Frappe's sign-in card. | `test_school_website.py::test_home_page_is_the_school_site` | [x] 23 Nov |
| 2 | The school has no portal, admissions or welfare licence | The Parent portal, Apply and Contact cards are hidden. Fees, Verify and Staff sign in remain. | `::test_cards_follow_the_licence` | [ ] |
| 3 | A Paybill number is set | The fees panel shows the Paybill and "admission number" as the account. With a Till, it shows Buy Goods and no account. | `test_website_logic.py::test_pay_steps*`, `::test_home_shows_fees` | [x] 23 Nov |
| 4 | Notices exist: one ticked for the website, one not, one expired | Only the ticked, unexpired notice appears. | `::test_only_website_notices` | [ ] |
| 5 | Terms exist for the current year | The term dates table lists them. With **Show term dates** off, it is hidden. | `::test_term_dates` | [x] 23 Nov |
| 6 | **Show the school homepage** is off | "/" goes to the sign-in page. | `::test_switched_off_goes_to_login` | [ ] |
| 7 | A guest opens /login | The school's name and colour show on the brand side, the parents' note is there, and Frappe's form (`login_email`, Forgot password) still works. Signing in still works. | `::test_login_is_branded` + by hand | [x] 23 Nov |
| 8 | Any web page with the standard navbar (e.g. /complaint) | The navbar shows the school's name, not "Home". | `::test_navbar_brand` | [x] 23 Nov |
| 9 | Signed in as staff, open "/" | The header button reads **Open the school system**. | `::test_signed_in_button` | [x] 23 Nov |
| 10 | The site is suspended | The page shows "The school portal is paused for now", the school's name and office contacts. The reason, amount due and **Check again** sit under "For school administrators". | `test_suspension.py` | [ ] (simulated only, never suspend a live school) |
| 11 | Phone width (390 px) | The menu folds, cards stack, nothing scrolls sideways. | by hand | [x] 23 Nov |
| 12 | A school colour that is too light (e.g. #3cbd4d) | Buttons use a darker shade that passes 4.5:1 with white text. | `test_website_logic.py::test_readable` | [ ] |

## Not broken

- [x] `./scripts/check.sh` and CI green
- [ ] Parent sign-in lands on the parent portal as before (CI; not tried live: needs a parent login)
- [x] /admission-status, /complaint-status and /verify still work (23 Nov, all 200 with the new header)
- [ ] Unlicensed school: unlicensed cards hidden

## Docs

- [x] `docs/SCHOOL_WEBSITE.md`
- [x] User guide section updated
- [x] `CHANGELOG.md`
