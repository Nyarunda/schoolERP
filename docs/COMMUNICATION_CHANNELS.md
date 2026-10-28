# Communication channels — Phase 1

School ERP already has **School Settings → SMS & Email**, an Africa's Talking adapter,
Frappe SMS Settings support, a custom sender hook, parent email via Frappe's outgoing
Email Account, and School Message bulk messaging. This change **extends those
existing components** rather than adding a competing notification engine.

## Master switches

On each school site, open **School Settings → SMS & Email**:

- **Enable Outgoing SMS Notifications**: disable to suppress SMS through
  `school_erp.api.messaging.send_sms` (including parent and staff messages).
- **Enable Outgoing Email Notifications**: disable to suppress parent emails
  through `school_erp.api.messaging.email_student`.

Both default to enabled to preserve behavior on existing schools; disable SMS
immediately on tenants without an approved provider or SMS budget. The toggles
apply per Frappe site, not across all tenants. Disabling a channel does **not**
alter platform-wide Frappe email, password resets, or administrator alerts.
It also does not govern other apps that call Frappe's SMTP or SMS sender
directly; those need separate integration work.

## Configure ZeptoMail

1. Verify the sending domain and sender in ZeptoMail.
2. Obtain the **SMTP username and SMTP credential** from the associated Mail
   Agent's SMTP/API page. Do not use a Zoho account password.
3. Create an **outgoing Email Account** within each school site that will send
   email; use `smtp.zeptomail.com`, port `587`, STARTTLS, certificate
   verification, and the Agent SMTP credentials.
4. Send a test email from the Frappe Email Account, then check **Email Queue**
   and the ZeptoMail delivery events.

Control Center (admin site) notification email is configured independently.
Keep SMTP credentials in Frappe's encrypted password storage and restrict
access to Email Account. Do not commit credentials.

## Configure SMS

Each school can select Frappe SMS Settings, Africa's Talking, or a custom hook.
For Africa's Talking, populate the username, API key, sandbox mode and the
approved Sender ID. Set **Enable Outgoing SMS Notifications** off until ready.

## Deferred to follow-up PRs

This is the first safe integration slice, **not** a completed multichannel
orchestration system. Next changes should add:

- A persisted delivery-attempt ledger with provider outcomes and idempotency.
- Quiet hours, consent/opt-out enforcement, per-event switches and SMS budgets.
- Post-commit dispatch and retries with bounded backoff.
- Explicit cross-app coverage (Frappe Notification, password reset, platform
  alerts) and provider integration tests.

No claim is made that delivery from ZeptoMail/Africa's Talking was verified
on a live server by this PR.
