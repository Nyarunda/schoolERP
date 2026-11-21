# Report cards per stream: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Scope by stream/class | — | `generate_report_cards(exam, stream, school_class)` computes the whole exam, writes only the target streams |
| Class teacher only | Stream.class_teacher, Teacher.user | `report_card_scope()`, `my_class_streams()`; managers = System Manager, School Admin, Head Teacher |
| Consistent class positions | — | After a scoped run, `class_position`/`class_size` refreshed on other streams' cards (no regeneration) |
| Bulk print | `frappe.utils.pdf.get_pdf` | `report_cards_pdf()` joins card bodies with page breaks; `download_report_cards` |
| Choosing in the UI | `frappe.ui.Dialog` | `report_card_options()` lists allowed streams with "marks waiting" / cards ready |

## Changes

| File | Change |
|---|---|
| `school_erp/api/exams.py` | Scope helpers, scoped generation, options, bulk PDF |
| `school_erp/school/doctype/exam/exam.js` | Results → Generate / Print Report Cards dialogs |
| `school_erp/tests/test_report_cards_per_stream.py` | Teacher scope, refusals, position refresh, bulk names/PDF |

## Data and migration

None: no new fields.

## Risks

Regenerating on a published exam must not unpublish cards or lose remarks (kept; status untouched).

## Deploy notes

JS changed: `bench build --app school_erp`.
