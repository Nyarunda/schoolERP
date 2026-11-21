# Every shilling through the General Ledger: requirements

*Branch: `feat/money-through-gl` · Roadmap item: #7 · Status: Agreed*

## Why

The owner: "in finance everything posting or money must pass through chart of accounts g/l account".

An audit (21 Nov 2026) found that fee billing (Sales Invoice), fee receipts and matched M-Pesa (Payment Entry) and
expenses (Journal Entry) already post. Four kinds of money do not, so the balance sheet and the cash book disagree
with what the school actually holds:

| Money | Today | Gap |
|---|---|---|
| Pocket money deposits, purchases, withdrawals | Only the learner's balance moves | Cash/M-Pesa received and the students' money the school holds are not in the books |
| M-Pesa payments not yet matched to a learner (Unmatched, Failed) | Waits in the M-Pesa inbox | Money is in the Paybill but not in the books until someone matches it |
| Library fines when Fees is off, "bill fines to fees" is unticked, or a teacher borrowed | A number on the loan | Cash collected for a fine is not recorded anywhere |
| Fuel bought by drivers | A figure in the Driver Daily Log | Spending that is not an expense |

## Who uses it

| Role | What they do with it |
|---|---|
| Bursar / Accounts | Sets the accounts once; sees every movement in the General Ledger and Trial Balance; reconciles |
| Shop / canteen staff | Records purchases exactly as today; the posting happens behind the scenes |
| Librarian | Marks a fine as paid (cash or M-Pesa) when it isn't billed to fees |
| Driver / Transport Manager | Logs fuel as today; an expense request is raised for approval |
| Head Teacher / approvers | Approve fuel expenses in the usual expense workflow |

## Must

1. **Pocket money posts every transaction** (owner's choice: the school runs the shop):
   - Deposit: Dr Cash / M-Pesa / Bank (the mode's account), Cr **Pocket Money Held** (liability).
   - Withdrawal (cash handed back): Dr Pocket Money Held, Cr Cash.
   - Purchase: Dr Pocket Money Held, Cr **Tuck Shop Sales** (income).
   - Refund (shop gives money back): Dr Tuck Shop Sales, Cr Pocket Money Held.
   - Adjustment In / Out: against **Pocket Money Adjustments**, Cr / Dr Pocket Money Held.
   - Cancelling a transaction cancels its journal entry. The journal entry is linked from the transaction.
   - Many small purchases must not flood the ledger: purchases may be posted as one journal entry per day per
     till user (owner can choose "each" or "daily summary"; default daily summary).
2. **Opening balance for schools already using pocket money**: one journal entry for the total of all balances,
   Dr **Temporary Opening**, Cr Pocket Money Held, dated the deploy date, so the ledger equals the learners'
   balances from day one. The bursar then moves Temporary Opening to the real cash/bank account.
3. **Pocket money reconciliation**: a check (button and report line) that Pocket Money Held in the General Ledger
   equals the sum of all learners' balances, showing the difference if any.
4. **Unmatched M-Pesa goes to suspense** (owner's choice): when a validated payment is Unmatched or Failed, post
   Dr M-Pesa clearing, Cr **Unidentified Receipts** at once. When it is later assigned to a learner, the suspense
   entry is cancelled and the normal Fee Payment posts, so suspense clears. If it is Ignored (e.g. refunded to the
   payer), suspense stays until the accountant clears it with a journal entry; the Unidentified Receipts balance
   shows what is outstanding.
5. Payments **Needs Review** (they failed security checks and may not be real money) are **not** posted until a
   senior person verifies them, as today; verifying posts them normally. *(Departure from the question as asked:
   posting an unverified confirmation could put fake money in the books.)*
6. **Library fines always reach the books**: billed to the fee account when Fees is on and billing is ticked
   (as today). Otherwise the librarian clicks **Fine Paid**, picks Cash or M-Pesa (and reference), and a journal
   entry posts Dr Cash / M-Pesa, Cr **Library Fines** (income). A fine can't be marked paid twice; waived fines
   post nothing.
7. **Fuel becomes an expense**: submitting a Driver Daily Log with a fuel cost raises a School Expense (category
   **Fuel**, payee the driver or fuel station, amount the fuel cost, linked back to the log) and sends it for
   approval. It posts to the Fuel expense account through the existing approval workflow. One expense per log;
   cancelling the log cancels a not-yet-approved expense and warns if it was already approved.
8. All new accounts are created automatically under the right groups when missing and shown in School Settings,
   where the bursar can change them. Nothing posts until the school has a company set; a clear message says which
   account is missing.
9. A **Money not in the ledger** check (in School Settings > Check Setup or the Accounts area): lists any submitted
   pocket money transaction, matched/unmatched M-Pesa payment, paid fine or approved fuel expense without a
   posting, so nothing can slip through again.

## Must not / out of scope

- No change to how fees, fee receipts or expenses already post.
- No change for shop staff: same screens, same speed; the posting never blocks a sale for longer than today.
- Does not post Needs Review payments, uncollected fines (they are not money yet) or Library Book prices.
- Does not rebuild past pocket money history transaction by transaction (the opening entry covers it).
- No vendor-run shop option (owner chose school-run); can be added later as a setting.

## Rules and permissions

- Journal entries are made by the system (`ignore_permissions`) as part of the user's allowed action: the shop user
  doesn't need Accounts rights.
- Only Bursar, Accounts Manager, School Admin may change the accounts in School Settings or run the opening entry.
- Licensing: pocket money postings only when `pocket_money` is enabled; suspense only with `mpesa`; fuel expense
  only with `transport` and `expenses`; fines with `library`.
- School Viewer can read the new fields and the reconciliation report.

## Open questions

- [x] Pocket money purchases: shop income (owner).
- [x] Unmatched M-Pesa: suspense account (owner).
- [x] Fines always post; fuel creates an expense (owner).
- [ ] Daily summary vs each purchase: defaulting to daily summary; owner can say otherwise.
