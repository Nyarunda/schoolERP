# Control Center: everything through the chart of accounts, and a clearer sidebar

*Branch: `feat/control-center-accounts` · Roadmap item: #11 · Status: Agreed*

Owner: "the control center can be improved, everything is going through chart of account add it make controls and
sidebar design and add more features best of best". Agreed plan (21-22 Nov): four PRs: (1) accounts + sidebar,
(2) Stemic expenses, (3) refunds and credit notes, (4) growth and health KPIs. Posting: **always on** once the
accounting company is set.

## Must (this PR)

1. **Posting is compulsory** once Stemic Settings > Accounting > Company is set (and ERPNext is installed): every
   invoice, payment, commission and payout posts, or is refused with the reason. The old "Post to accounts" switch is
   retired (hidden).
2. **Post Missing Entries**: posts older records not in the books (invoices, then payments, commissions, payouts),
   oldest first; one refused (closed period) does not stop the rest; the result lists what was posted and what not.
   Runs once by itself on migrate.
3. **Check Ledger**: lists anything not posted, and any invoice whose amount owed differs between the Control Center
   and its Sales Invoice. Setup Check shows "Everything in the books".
4. **Sidebar redesign**: Home, KPI Overview; **Schools**, **Billing**, **Agents**, **Accounts** (Chart of Accounts,
   Journal Entry, Sales Invoice, Payment Entry, Bank Reconciliation, General Ledger, Trial Balance, Profit and Loss,
   Balance Sheet, Cash Flow, Accounts Receivable, Accounts Payable), **Tax (eTIMS)** (tax invoices, profiles, settings),
   **Operations** (backups, site operations, messages), **Setup**. Laid out by `scripts/regroup_platform_sidebar.py`
   (checked in check.sh).

## Must not
- No change to how each record posts (accounts, amounts); no posting without a company chosen.
