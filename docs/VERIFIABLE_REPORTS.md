# Verifiable SchoolERP documents — review implementation

## Included
- **Fee Payment**: issue a QR-stamped PDF only after receipt submission AND linked Payment Entry submission.
- **Report Card**: issue only when published.
- **Verified Document**: tenant-local registry with unique unpredictable reference, private PDF attachment, SHA-256, issuer, issue time, and revocation.
- **Public page**: `/verify?code=<opaque-reference>`, returns only validity, document type, issue date and configured school label; no student details, amounts, marks or source document.
- **PDF integrity**: users can optionally choose the issued PDF in their browser. Its SHA-256 is computed **locally** (file is not uploaded), and only the fingerprint is checked against the registry.
- **Reissue**: revokes previous valid PDF versions for the same source.
- **Cancellation**: a cancelled Fee Payment or an unpublished Report Card is treated as Revoked even if its verification record wasn't explicitly revoked.
- **Staff actions**: `Issue Verified PDF` buttons on submitted Fee Payment and published Report Card forms.
- **Site isolation**: each Frappe site has its own Verified Document table. Only the tenant's own verification endpoint can check those documents.

## Installation and trial
On a disposable SchoolERP site after checking out this branch:

```bash
cd ~/frappe-bench
./env/bin/pip install -e apps/school_erp
bench --site school.localhost migrate
bench build --app school_erp
bench --site school.localhost clear-cache
```

Set a public HTTPS `host_name` or appropriate Frappe site URL so generated QR links point to the correct public school hostname. Optionally set `school_verification_label` in that site's config. Custom-domain host routing must point to the **same tenant site**. A document issued under one school site must not resolve against another school's database.

1. Open a **submitted** Fee Payment with a submitted linked Payment Entry.
2. Click **Issue Verified PDF** and download the newly attached **private** PDF. Inspect QR, code, and visible text in the PDF before considering it issued.
3. Open the QR URL or `https://<school-host>/verify?code=<reference>` on a separate device. It should report Valid.
4. Select the exact downloaded PDF in the verification page. It should report Exact Match. Editing a copy should return No Match.
5. Reissue the same receipt: old code must return Revoked, new code Valid.
6. Cancel a receipt in a disposable test site: verification must return Revoked.
7. Repeat with a **Published** Report Card; drafts must be refused.
8. Try unauthenticated issue/revoke requests, other roles, bad token, missing token, an invalid SHA-256, and attempts to open the private file directly as Guest.

Test scripts: `pytest school_erp/tests/test_document_verification_policy.py` and `bash scripts/check.sh`.

## Limitations / production gates

**Not independently tested in running Frappe by the assistant.** Verify wkhtmltopdf (or site's PDF engine) renders data-URI QR images and the full document layout correctly; some PDF engines restrict data URI images. The saved artifact is authoritative, not a dynamically re-rendered HTML page.

- A verification code is a bearer locator. Protect access logs and use rate limiting at the public edge.
- SHA-256 detects differences between files, not a cryptographic signature from Safaricom or a trusted third-party authority.
- Verification status is hosted by the issuing tenant site; a compromised administrator/database could alter the registry. Cross-tenant, independently signed attestations or a central append-only Stemic verification index remain future work.
- This does **not** implement a separately versioned *fee statement*, admission letter, clearance/transfer certificate, or USSD verification. Those require dedicated issuance flows and document authorization rules.
- No public personal data, fees, marks, or PDF download is returned by the API.
- For PDFs printed through other routes, verification is only available when the **Issued Verified PDF** action is used. An ordinary printout lacks this guarantee.
- Retain private PDF backups, audit events, and robust tenant-specific URLs. Do not allow an unauthenticated user to request issuance.

## Extended document support (review update)

- **Fee Statement**: call `school_erp.api.document_verification.issue_statement` with `student`, optional `from_date` and `to_date`. This issues a time-bound PDF snapshot using the existing fee statement rendering logic. Later changes to fees do not alter that issued historical file. The method is restricted to authorized issuing staff.
- **School Certificate**: create a Draft `School Certificate`, select Admission Letter / Transfer Letter / Clearance Certificate, and enter the official text. Approve, issue a private QR-stamped PDF, and revoke through the form buttons.
- A certificate may not be issued until approved. Once approved, protected letter content cannot be edited through a normal document save.
- The public `/verify` endpoint keeps disclosing only status, document type, issue timestamp, and configured issuer label.

**Still outstanding and not claimed as implemented:** a central cross-tenant verification registry/service and telco-connected USSD verification. These require secure school identity federation, independent signing/storage, an external USSD gateway shortcode/credentials, provider callbacks, abuse controls and data-minimization reviews. A fake USSD simulator is not a production USSD implementation.

**Tests not executed by the assistant.** Install/migrate on a disposable Frappe site and verify approval, issuance, historical statement PDF, revocation, exact hash matching, private file restrictions, and page rendering before deployment. Keep PR in draft until tested.
