# Stemic School Control — Kenya eTIMS integration foundation

## Status
This feature is a **preparation and tax-review module only**. It does not call KRA, certify OSCU/VSCU, create control unit signatures, generate official CU QR codes, submit or confirm invoices, or register the business for tax. `Submitted` and `Rejected` remain reserved for a future provider-verified adapter. Never show a draft/ready invoice as KRA-accepted.

## KRA guidance and tax classification
KRA requires persons in business, including schools supplying VAT-exempt educational services, to onboard on eTIMS where applicable. VAT-exempt is **not** the same as zero-rated. Other activities (e.g. sales outside educational services) can have distinct VAT treatment. A qualified Kenyan tax adviser must classify each supply against current law. The standard VAT rate published by KRA is 16%, but the module deliberately does not auto-apply VAT to every school supply.

- https://www.kra.go.ke/business/etims-electronic-tax-invoice-management-system/learn-about-etims/what-is-etims
- https://www.kra.go.ke/business/etims-electronic-tax-invoice-management-system/learn-about-etims/etims-system-to-system-integration
- https://www.kra.go.ke/individual/filing-paying/types-of-taxes/value-added-tax

KRA supports direct OSCU (online) and VSCU (bulk/offline) integrations subject to sandbox testing/certification, or a KRA-verified integrator. Consult the actual specification that corresponds to the licensed provider and version before sending payloads.

## Data and APIs
- `SaaS Tax Profile`: one per **school tenant acting as seller** with seller PIN, branch, preferred mode, default classification. Enabled profile required before preparing an invoice.
- `SaaS eTIMS Invoice`: immutable source-reference audit record with customer name/PIN, seller PIN, manual approved tax treatment, exact monetary totals, source fingerprint and processing status.
- `stemic_control.etims.prepare_invoice` (POST): authorized administrator prepares one source invoice. Deduplication uses deterministic tenant+invoice reference; conflicts are refused.
- `stemic_control.etims.approve_invoice` (POST): promotes Draft to Ready only after staff review. Does **not** submit to KRA.
- `stemic_control.etims.compliance_overview` (GET): admin-only counts in the School Control dashboard.

**Scope boundary:** This model covers **school-issued invoices for their customers**. When Stemic the SaaS company invoices a school for subscription services, **Stemic** (not the school) is the seller and must use its own legal entity tax profile. Do not reuse a school's KRA PIN as the seller for SaaS subscription invoices. Platform-issued billing is not connected by this PR.

## Integration plan before go-live
1. Verify legal business identity and KRA PIN and collect approved OSCU/VSCU/integrator credentials per registered seller and branch.
2. Map ERPNext submitted Sales Invoice, returns, credit notes, item classifications, applicable tax codes, buyer PIN, tax-inclusive/discount rounding and time-zone requirements to approved provider schema.
3. Store a durable, idempotent outbox; submit asynchronously using signed/credentialed TLS; distinguish transient errors from validation rejections; never fabricate a CU invoice number.
4. Persist signed authority acknowledgement, official document numbers/QR, tax breakdown and original request hash. Separate display receipt from official KRA invoice status.
5. Implement credit notes through the same original issuing solution, not an unrelated one.
6. Reconcile invoices, provider acknowledgements, cash receipts, returns and accounting journals daily. Provide reprocessing / disputes with immutable audit records.
7. Complete Kenya compliance/legal tests and tenant isolation and back up evidence before live enablement.

## Installation and tests
On the Stemic Control *admin site only*, update branch, `bench --site admin.localhost migrate`, and rebuild the app. `PYTHONPATH=platform/stemic_control python -m pytest platform/stemic_control/stemic_control/tests/test_tax_rules.py` tests the pure money/tax helpers outside Bench.

Production gates: schema installation, permissions, manually approved tax classification, KRA sandbox certification, provider adapter, live issuer credentials, end-to-end acknowledgment and reversal tests. The assistant has not run these tests on the user's instance.

## Examples
Preparing an **exempt** school education supply only if legal classification is verified:

```python
frappe.call("stemic_control.etims.prepare_invoice", {
    "tenant": "school-slug",
    "external_invoice_no": "INV-2026-0001",
    "buyer_name": "Parent or purchasing organization",
    "buyer_pin": None,
    "net_amount": "10000.00",
    "vat_amount": "0.00",
    "total_amount": "10000.00",
    "tax_treatment": "Exempt",
})
```

This creates an internal **Draft**, not a tax invoice registered at KRA.


## Stage 2: submission workflow and seller segregation

The same invoice registry now distinguishes `seller_scope = School` from `Stemic Platform`. Stemic platform subscription sales require a separately enabled `Stemic Tax Settings` Single DocType. The school tenant is the **buyer** for these invoices, not the registered seller.

New operations:
- `stemic_control.etims.queue_submission(name)`: authorizes the admin, enforces Ready status and explicit site-config opt-in; queues only.
- `stemic_control.etims.submit_queued(name)`: background worker invokes a deployment-installed certified provider adapter. HTTP success **does not** equal KRA acceptance.
- `stemic_control.etims.invoice_history(name)`: read-only audit history.
- `stemic_control.etims.reconciliation_summary()`: operational status summary.
- The invoice form adds Approve, Queue and History actions.
- Audit events are append-only through the service path.

Provider adapter is **not included**: each licensed integration must implement its approved KRA OSCU/VSCU or certified intermediary protocol and **independently verify** the KRA acknowledgement. No production credentials are bundled. Configure through per-site private site_config values only after implementation and certification:

```json
{
  "stemic_etims_live_enabled": 0,
  "stemic_etims_adapter": "stemic_control_integrations.your_certified_provider.submit"
}
```

Adapter is a trusted Python function receiving a tenant-bound invoice dict and returns one of:

- `{"status": "pending"}`: no conclusive acknowledgement, remain Pending Submission.
- `{"status": "rejected", "reason": "..."}`: explicit verified tax authority/provider rejection.
- `{"status": "accepted", "signature_verified": true, "provider_reference": "...", "kra_invoice_number": "...", "verification_evidence": "..."}`: only after independent verification of the returned authority control-unit evidence.

The adapter must be installed by the deployment administrator, authenticate securely, make submission idempotent using `invoice_key`, provide lookup/reconciliation of uncertain outcomes and never blindly set `signature_verified`. This integration boundary is **not a certified KRA submission service on its own**. Retry a Pending Submission only by querying the upstream provider using its idempotency key, never by reissuing a new invoice blindly.

The original School customer workflow and the platform subscription seller flow have different legal sellers; do not use a school PIN for Stemic invoices. All exempt/zero-rated/standard treatment remains subject to accountant review.

**Still external to this PR:** provider mapping, credentials, signing/receipt-QR fields, a working bank/M-Pesa settlement reconciliation, provider lookup/retry workflow, tax authority certification and live end-to-end acceptance. Live configuration stays disabled until those exist.


### Stemic subscription invoice preparation

Administrators can prepare the Stemic SaaS company's own eTIMS invoice with `stemic_control.etims.prepare_platform_subscription_invoice`. Supply the approved accounting invoice reference, subscription ID, reviewed amount breakdown, tax treatment and optional school buyer PIN. The legal seller is the separate `Stemic Tax Settings` tax identity, not the customer's `SaaS Tax Profile`.

This is not a billing-ledger engine; the accounting source invoice must be created and reconciled separately, and discounts/credit notes must be represented accurately before a certified integration is enabled.
