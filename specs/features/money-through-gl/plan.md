# Every shilling through the General Ledger: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| 1 Pocket money postings | ERPNext Journal Entry (submit/cancel makes and reverses GL Entries) | `logic/ledger.py`: the Dr/Cr lines for each transaction type (pure, unit tested); `api/ledger.py`: build/submit/cancel JE |
| 1 Daily purchase summary | Scheduler (daily) + Journal Entry | `ledger.post_purchase_summaries()`: one JE per day per till user for unposted purchases; transactions get the JE link |
| 2 Opening entry | Journal Entry, ERPNext "Temporary Opening" account | patch `pocket_money_opening_entry` (once, only if balances exist and no opening yet) |
| 3 Reconciliation | GL balance (`get_balance_on`) | `ledger.pocket_money_reconciliation()` + button on Pocket Money Account list / report line |
| 4 M-Pesa suspense | Journal Entry; cancel on match | `paybill._post`: on Unmatched/Failed call `ledger.post_suspense(tx)`; on Posted cancel `tx.suspense_entry` first |
| 6 Library Fine Paid | Mode of Payment default account; Journal Entry | `library.fine_paid(name, mode, reference)` + button |
| 7 Fuel expense | Existing School Expense + Workflow "School Expense Approval" | `DriverDailyLog.on_submit` → `transport_ops.raise_fuel_expense(log)`; `on_cancel` handling |
| 8 Accounts | Account DocType; same pattern as `tax.ensure_accounts` | `ledger.ensure_accounts(settings)` called from School Settings save and patch |
| 9 Money not in ledger | — | `ledger.unposted_money()` + "Check ledger" button in School Settings |

Shared helper: `ledger.journal(lines, posting_date, remark, reference)` (company, cost center from School Settings,
`ignore_permissions`, insert + submit) used by every posting above; `expenses.make_journal_entry` stays as is.

## Changes

| File | Change |
|---|---|
| `school_erp/logic/ledger.py` | `pocket_money_lines(type, amount, mode_account, accounts)`, `fine_lines`, `suspense_lines`, `summarise_purchases(rows)` |
| `school_erp/api/ledger.py` | `ensure_accounts`, `journal`, `cancel_journal`, `post_pocket_money`, `post_purchase_summaries`, `post_suspense`, `pocket_money_reconciliation`, `unposted_money`, `post_pocket_money_opening` |
| `school_erp/api/pocket_money.py` | `post()` / `unpost()` call the ledger (purchases in daily mode wait for the summary; cancelling a summarised purchase is refused after its day is posted unless the bursar reverses the summary) |
| `school_erp/api/paybill.py` | suspense on Unmatched/Failed; cancel suspense before the Fee Payment |
| `school_erp/api/library.py` | `fine_paid` |
| `school_erp/api/transport_ops.py` | `raise_fuel_expense`, cancel handling |
| DocTypes | Pocket Money Transaction `journal_entry`; M-Pesa Transaction `suspense_entry`; Library Loan `fine_paid_entry`, `fine_paid_mode`, `fine_paid_reference`; Driver Daily Log `fuel_expense`; School Settings section **Ledger accounts**: `pocket_money_account`, `tuck_shop_income_account`, `pocket_money_adjustment_account`, `pocket_money_purchase_posting` (Daily summary / Each purchase), `pocket_money_bank_mode`, `unidentified_receipts_account`, `library_fines_account`, `fuel_expense_category` |
| JS | Library Loan **Fine Paid** dialog; Pocket Money Account list **Check Ledger**; School Settings **Check Ledger** |
| `hooks.py` | daily `post_purchase_summaries` |
| patches | `create_ledger_accounts`, `pocket_money_opening_entry`, `suspense_for_open_mpesa` (existing Unmatched/Failed) |
| tests | `tests/test_logic.py` ledger lines; `tests/test_money_through_gl.py` integration per acceptance line |

## Data and migration

- New accounts (created only if missing, by name, per company): Pocket Money Held (Liability, under Current
  Liabilities), Tuck Shop Sales (Income), Pocket Money Adjustments (Expense, under Indirect Expenses), Unidentified
  Receipts (Liability), Library Fines (Income); Expense Category **Fuel** → "Fuel & Transport" account (Expense).
- Opening entry: sum of `Pocket Money Account.balance`; skipped if zero or already made (flag in School Settings).
- Existing Unmatched/Failed M-Pesa rows get a suspense entry dated their transaction date.
- Past driver logs and past paid fines are not back-posted (no reliable record of how they were paid).

## Risks

- **Live school (mogongapagsecondary)**: the opening entry and suspense entries change its balance sheet. Mitigation:
  backup first; entries are clearly labelled; Temporary Opening is the standard ERPNext holding account; the
  bursar is told to reclassify. If pocket money/M-Pesa aren't licensed there, nothing posts.
- **Closed accounting periods / frozen accounts**: a JE would fail. The patch logs and reports instead of crashing
  migrate; `unposted_money` lists what still needs posting.
- **Shop speed**: daily summary keeps purchases free of JE work; each-purchase mode adds one JE per sale.
- **Double counting fuel**: schools already entering fuel expenses by hand would count twice. Setting on the
  Expense Category link: no Fuel category chosen = feature off. New schools get it on; existing schools get it on
  too, with the CHANGELOG/guide telling bursars to stop manual fuel entries.

## Deploy notes

Backup first (`bench --site all backup --with-files`), migrate (new fields, patches), `bench build --app school_erp`
(new buttons), restart.
