# Delete a school from the Control Center: requirements

*Branch: `feat/delete-school` (on top of #89, #90) · Roadmap item: #10 · Status: Agreed*

## Why

Owner: "a way to delete school from admin, then it deletes even the site and databases and backups". Today a school
that leaves (or a test/demo school) can only be suspended; its site, database and backups stay on the server forever.

Owner's choices: **remove everything** (also invoices, payments and the school record); **7-day grace**; keep **one
final copy off-server for 90 days**.

## Must

1. **Delete School** on the school (platform admins only). The dialog shows what will go (site, database size,
   backups, domains, invoices, payments, commissions, licences) and needs `DELETE <slug>` typed to confirm.
2. **Grace of 7 days**: the school is suspended at once (its users see the suspension page) and a **SaaS Deletion**
   record is scheduled. **Cancel Deletion** until then puts the school back as it was (unsuspended if it was Active).
   Platform admins are reminded the day before.
3. **On the day** (daily job, one school at a time, or **Delete Now** on a scheduled deletion after the grace period):
   - a **final backup** (database + files) is taken and kept **90 days**: off-server when storage is set up,
     otherwise in the bench's `stemic-final-copies/<site>/` folder; then removed automatically;
   - the **site and its database are dropped** (`drop-site --no-backup`), and Frappe's archived copy of the site
     folder is removed too;
   - **every other backup** is removed: on the server and off-server;
   - **domains** are removed (the server routes follow on the next hourly sync);
   - **money and other records**: payments and invoices are cancelled (their ERPNext entries reversed) and deleted;
     commissions, licences, subscriptions, communications, provisioning jobs, site operations and tax profile are
     deleted; the ERPNext customer and its cancelled entries are deleted where nothing else uses them;
   - the **school record** is deleted.
4. **Tax records are kept** (exception to "remove everything", see below): a school with eTIMS tax records keeps them,
   plus any invoice already with KRA (Pending Submission / Submitted) and its payments, and its school record stays as
   status **Deleted**. Everything else is removed as above.
5. A **SaaS Deletion** record stays as the audit trail (not linked, so it survives): school name, slug, site, who asked,
   when scheduled, when done, what was removed, final copy, errors. A failed deletion is retried with **Retry**.

## Must not

- No deletion while another operation runs on the site; no deletion of the admin site itself.
- Never removes files outside the school's own site folder, its archived copy, or its final-copy folder.
- No secrets in output.

## Tax records (why the exception)

Tax invoices sent to KRA are fiscal records: the Control Center already refuses to delete or cancel them (a credit
note is required). Deleting the local copy would not remove them at KRA and would leave Stemic unable to show them in an
audit. So they, and the invoices they belong to, are kept.
