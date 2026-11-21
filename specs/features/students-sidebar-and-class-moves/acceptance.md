# Clearer sidebar, graduate a learner, move a learner back: acceptance

| # | Given / when | Then | Test | On test site |
|---|---|---|---|---|
| 1 | The new sidebar | Every link from before is there exactly once, in the sections of the plan | `scripts/regroup_sidebar.py --check` in check.sh | [ ] |
| 2 | Status → Graduate on an active learner | Status Graduated, leaving date set; in Graduated Students | `test_graduate_and_readmit` | [ ] |
| 3 | Re-admit a graduated learner | Active again, leaving details cleared | `test_graduate_and_readmit` | [ ] |
| 4 | Move Class from Grade 5 East to Grade 4 East, reason Repeating | Class and stream changed; timeline says moved back, with reason and who | `test_move_class_back_records_why` | [ ] |
| 5 | Learner has an invoice this term | Move still happens; a warning names the invoice | `test_move_warns_about_invoice` | [ ] |
| 6 | Select 2 learners → Move to Stream / Mark as Graduated | Both moved / graduated; errors reported per learner | `test_bulk_actions` | [ ] |
| 7 | Completed promotion → Move a Student Back | Learner back in the stream they came from; promotion line marked "Moved back" | `test_move_back_from_promotion` | [ ] |
| 8 | A user without write access to students | All of the above refused | `test_needs_write_permission` | — |
| 9 | Levels 5 → 4, 4 → 5, 4 → 4 | back, up, same class | `test_logic.py::test_move_kind` | — |

## Not broken

- [ ] CI green
- [ ] Unlicensed school: empty sections disappear
- [ ] Year-end Promotion still promotes

## Docs

- [ ] User guide: sidebar paths, Graduate, Move Class, Move a Student Back
- [ ] `CHANGELOG.md`
