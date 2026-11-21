# <Feature name>: plan

*How the requirements are met. Standard Frappe/ERPNext first (see `specs/tech-design.md`); custom code only where
nothing standard fits.*

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| | | |

## Changes

| File | Change |
|---|---|
| `school_erp/logic/…` | Pure rule, unit tested |
| `school_erp/api/…` | Whitelisted method, permission checks |
| `school_erp/school/doctype/…` | Fields / controller |
| `…js` | Buttons, dialogs |
| `school_erp/school/sidebar/school/school.json` | Links (bump `modified`) |
| `tests/…` | Unit + integration tests |

## Data and migration

New fields, defaults for existing schools, patches, anything `migrate` must create.

## Risks

What could break for live schools, and how the plan avoids it.

## Deploy notes

`bench build` needed? Backup first? Anything the owner must do by hand?
