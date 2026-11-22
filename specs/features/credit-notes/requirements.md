# Refunds and credit notes: requirements

*Branch: `feat/credit-notes` (on #95) · Roadmap item: #13 · Status: Agreed*

Owner (22 Nov): Control Center features "best of best", everything through the chart of accounts. Today a wrong or
disputed invoice can only be cancelled (impossible once paid or filed with KRA), and money can't be given back.

## Must
1. **SaaS Credit Note** on a submitted invoice: amount (incl. VAT, up to what is left to credit), reason, notes;
   optionally **refund** money to the school (mode, reference).
2. What a school owes = total − credited − (paid − refunded). Invoice shows Credited / Refunded and status **Credited**
   when fully credited. Payments can't exceed the new balance. Only money paid beyond what is owed after the credit can
   be refunded, and never more than the credit.
3. **Books** (compulsory posting): Sales Invoice return against the invoice's Sales Invoice (income, deferred income and
   VAT reversed; outstanding reduced); refund = Payment Entry (Pay) to the school from M-Pesa / bank / cash. Cancel
   reverses both. Check Ledger / Post Missing Entries include them.
4. **KRA**: if the invoice's tax invoice is with KRA, the credit note is flagged *KRA credit note: Needed* and admins
   alerted; entering the KRA credit note number marks it Done. (Sending credit notes to eTIMS automatically is not built:
   the eTIMS module has no credit-note integration yet.)
5. A refund on an invoice that earned agent commission alerts admins to review the commission.
6. **Credit / Refund** button on the invoice; **Credit Notes & Refunds** in the Billing sidebar group.
