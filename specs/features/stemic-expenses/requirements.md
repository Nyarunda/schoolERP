# Stemic expenses: requirements

*Branch: `feat/stemic-expenses` (on #94) · Roadmap item: #12 · Status: Agreed*

Owner (22 Nov): "everything is going through chart of account". Stemic's own spending (hosting, SMS, domains, salaries,
marketing...) had nowhere to go in the Control Center.

## Must
1. **Expense Categories** (13 defaults: Hosting & Servers, SMS & Messaging, Domains & SSL, Software & Subscriptions,
   Salaries & Wages, Marketing & Sales, Transport & Travel, Internet & Phone, Office & Rent, Bank & M-Pesa Charges,
   Professional Fees, Taxes & Licences, Other Expenses), each with its own account under Indirect Expenses (created).
2. **Stemic Expense**: date, category, paid to, what for, amount incl. VAT, claimable VAT, paid by (M-Pesa, Bank
   Transfer, Card, Cash), reference, receipt, optional school. Draft = to approve; **Submit = approve and post**:
   Dr category account (amount − VAT), Dr Input VAT, Cr M-Pesa / bank / cash. Cancel reverses. Refused with the reason
   when no accounting company (posting is compulsory).
3. **Repeat every month**: next month's draft is prepared on the day for an admin to confirm (alerted).
4. **This Month** (costs by category vs collected, commission, left over) and the **Costs vs Revenue** report (per month,
   one column per category, chart, totals).
5. Check Ledger / Post Missing Entries include expenses. Sidebar group **Expenses**.

## Must not
- No expense recorded in the books without approval; no edit after submit (cancel and amend).
