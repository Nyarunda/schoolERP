# Report cards per stream: acceptance

| # | Given / when | Then | Test | On test site |
|---|---|---|---|---|
| 1 | Class teacher of East opens Generate | Only East is listed | `test_class_teacher_generates_and_prints_own_stream` | [ ] (needs a teacher login) |
| 2 | Teacher asks for West, the class, or the whole exam | Refused with a clear message | same | [ ] |
| 3 | Generate East only | Only East's cards change; class position out of all streams | same | [x] Grade 1 East: 6 cards, values unchanged, West untouched |
| 4 | West generated after East | East's class position/size refreshed (2/2 → 2/4) | same | [x] (positions consistent, 12 in class) |
| 5 | Regenerate a published exam | Cards stay Published, remarks kept | — | [x] |
| 6 | Print Report Cards for a stream | One PDF, one page per learner | bulk names/PDF in test | [x] 6 pages for Grade 1 East |

## Not broken

- [x] CI green
- [x] Publishing unchanged

## Docs

- [x] User guide section 6 step 4 (generate per stream, print the stream)
- [x] `CHANGELOG.md`
