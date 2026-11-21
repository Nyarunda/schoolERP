# Report cards per stream: requirements

*Branch: `feat/report-cards-per-stream` · PR #79 · Status: Done (2026-11-14). Written after the fact as the first
worked example of a feature spec.*

## Why

The owner: "Report card to be generated per stream per class, each teacher to generate theirs in bulk."
Before, **Generate Report Cards** rebuilt every card in the school at once, any teacher could trigger it, and cards
downloaded one at a time.

## Who uses it

| Role | What they do with it |
|---|---|
| Class teacher | Generates and prints the report cards of their own stream(s) |
| Head Teacher, School Admin | Generate any stream, a whole class, or the whole exam; publish to parents |

## Must

1. Generate for one stream, one class (all its streams) or the whole exam.
2. A class teacher (Stream → Class Teacher → Teacher → login) can do only their own streams.
3. Class positions always count every stream of the class, and stay right whatever order streams are generated in.
4. Remarks already written are kept when cards are regenerated.
5. Print a whole stream (or class) as one PDF, one card per page.

## Must not / out of scope

- Change publishing: still Head Teacher/Admin, once per exam.
- Touch other streams' marks or remarks.

## Rules and permissions

`exams` module. Report Card create needed to generate; read to print. Scope checked on the server
(`report_card_scope`), not only in the dialog.
