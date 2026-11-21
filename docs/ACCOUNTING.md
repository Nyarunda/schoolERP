# Where school money posts in the General Ledger

Every shilling the system records reaches the chart of accounts. Fees, receipts and expenses post through standard
ERPNext documents; the rest posts as Journal Entries made by the system. Accounts marked *(auto)* are created when
School Settings is saved and can be changed in **School Settings > Accounts & IDs > Ledger accounts**.

| Money | Document | Debit | Credit |
|---|---|---|---|
| Term fees billed | Sales Invoice | Debtors (learner) | Fee income (Fee Type or Default Income Account) |
| Fee paid (cash, bank, M-Pesa matched) | Payment Entry (from Fee Payment) | Mode of payment account | Debtors |
| M-Pesa paid, learner not known yet (Unmatched / Failed) | Journal Entry | M-Pesa account | Unidentified Receipts *(auto)* |
| ...later assigned to a learner | suspense entry cancelled + Payment Entry | M-Pesa account | Debtors |
| Pocket money deposit | Journal Entry | Cash / M-Pesa / Bank | Pocket Money Held *(auto, liability)* |
| Pocket money withdrawal | Journal Entry | Pocket Money Held | Cash |
| Shop purchase (one entry per day per till by default) | Journal Entry | Pocket Money Held | Tuck Shop Sales *(auto, income)* |
| Shop refund | Journal Entry | Tuck Shop Sales | Pocket Money Held |
| Pocket money adjustment in / out | Journal Entry | Pocket Money Adjustments / Held | Held / Pocket Money Adjustments *(auto)* |
| Balances held when posting started | Journal Entry (once) | Temporary Opening | Pocket Money Held |
| Library fine billed to fees | Sales Invoice | Debtors | Library Fine fee type income |
| Library fine paid at the library | Journal Entry | Cash / M-Pesa | Library Fines *(auto, income)* |
| Approved expense (incl. fuel raised from a driver log) | Journal Entry | Expense category account (Fuel & Transport *(auto)* for fuel) | Mode of payment account |

## Bursar checklist

- **After the update**: move the *Temporary Opening* amount to the account where pocket money is really kept
  (a Journal Entry: Dr cash/bank, Cr Temporary Opening).
- **Unidentified Receipts** should go back to zero: assign each Unmatched M-Pesa payment to its learner, or clear a
  refunded one with a Journal Entry.
- **Fuel**: with "Raise a Fuel expense from driver logs" on, stop entering fuel expenses by hand.
- **Check Ledger** (School Settings, or the Pocket Money Account list): confirms Pocket Money Held equals the learners'
  balances and lists any record not yet in the ledger.
- Payments **Needs Review** are not posted until a senior person verifies them: they failed security checks.
