# M-Pesa Paybill auto-posting

Parents pay the school Paybill and type the **Student ID** as the **Account Number**. Within seconds the payment is posted to that student: a Fee Payment is submitted, the ERPNext Payment Entry is created, the balance goes down, and the parent gets the receipt SMS with the new balance.

```
Parent pays Paybill 247247, Account STU-2026-0042, KES 15,000
        │
        ▼
Safaricom ──POST──► https://school.example.com/api/method/school_erp.api.paybill.confirm?token=…
        │                     │
        │                     ├─ stores "M-Pesa Transaction" SGL31HK2BO  (once only; retries are ignored)
        │                     └─ background job: find student → submit Fee Payment (oldest balance first)
        ▼
Parent SMS: "Received KES 15,000 for Amani (STU-2026-0042), ref SGL31HK2BO. New balance: KES 25,000."
```

**Account number matching** ignores case, spaces and hyphens: `stu 2026 0042`, `STU20260042` and `STU-2026-0042` all match. The admission number also works. A payment whose account number matches nobody (or matches two students) is saved as **Unmatched**. The bursar opens it from **Paybill Transactions**, clicks **Post to Student**, and picks the child. No money is ever lost or posted twice.

It is a licensable module: include `mpesa` (plus `fees`) in the school's license key.

---

## 1. What the school needs

| Item | Where it comes from |
|---|---|
| A **Paybill** (business short code) | The school's bank / Safaricom M-PESA business account |
| **Daraja app**: Consumer Key + Consumer Secret | https://developer.safaricom.co.ke → My Apps. Use a sandbox app first, then **Go Live** to get production keys linked to the real paybill (the paybill's M-PESA org portal admin approves it). |
| A **public HTTPS address** for the school's site | The production server, e.g. `https://greenhill.example.com`. Safaricom must reach it from the internet. |
| A Mode of Payment for M-Pesa | Created by *Run School Setup*. Set its **default account** for the company to the M-Pesa / Paybill clearing account (or the bank account the paybill settles into). |

Safaricom's rules for callback URLs:

* **HTTPS** in production (plain http is accepted only in sandbox).
* The URL (domain or path) must **not contain** `mpesa`, `m-pesa`, `safaricom`, `exec`, `exe`, `cmd`, `sql` or `query`. That's why the endpoints are named `paybill.confirm` / `paybill.validate`. Don't call your domain `school-mpesa.example.com`.
* Public tunnels (ngrok etc.) are not acceptable in production.

---

## 2. Configure (School Settings → M-Pesa tab)

1. Tick **Auto-post Paybill payments**.
2. **Environment**: `Sandbox` while testing, `Production` when live.
3. **Paybill Short Code**: e.g. `247247` (sandbox: the test short code shown on your Daraja app, usually `600xxx`).
4. **Daraja Consumer Key / Secret**: from the Daraja app (the secret is stored encrypted).
5. **Mode of Payment for Paybill**: `M-Pesa` (with its account set, see above).
6. **Public Site URL**: `https://greenhill.example.com`.
7. **If our site is unreachable**: leave **Completed**. Safaricom then still accepts the parent's payment if your server is down. You'll see it in the Daraja/org portal and can add it later (see section 6).
8. **Save**. A secret callback token is generated and the two callback URLs appear at the bottom.
9. Click **M-Pesa → Register URLs with Safaricom**. Do this once per paybill, and again if the site address changes.

Optional security, recommended in production:

* **Only accept callbacks from Safaricom IPs**: tick it. The allowed ranges default to `196.201.212.0/24`, `196.201.213.0/24` and `196.201.214.0/24` (community-documented; confirm with Safaricom). If your site sits behind a proxy or load balancer, make sure Frappe sees the real client IP (nginx `X-Forwarded-For` / `real_ip`), otherwise every callback is refused.
* Callbacks without the correct token are always refused and logged in **Error Log**.

### Rejecting wrong account numbers (optional)

By default every payment is accepted, and unknown account numbers become *Unmatched* for the bursar. If the school prefers Safaricom to **refuse** the payment when the account number isn't a Student ID:

1. Email **apisupport@safaricom.co.ke** asking to enable **External Validation** for the paybill (takes a few hours).
2. Tick **Reject unknown account numbers**, then **Register URLs** again.

The parent then gets an "invalid account" failure on their phone and keeps their money. Trade-off: if your site is down, validation can't answer, and what happens then depends on the "If our site is unreachable" setting.

---

## 3. Test it

### a) Offline, in WSL (no internet or Safaricom needed)

School Settings → **M-Pesa → Test Payment (offline)**. Enter a real Student ID (try it in lowercase without hyphens), an amount and a payer name. It runs the **exact same code** as a real Safaricom callback and shows the resulting status and Fee Payment. Allowed only in Sandbox or developer mode, because it creates real accounting entries. Use your `school.localhost` test site.

Automated: `bench --site test.localhost run-tests --app school_erp` includes paybill tests (auto-post, messy account numbers, Safaricom retries not double-posting, unmatched → assigned, cancel → not re-posted, license required).

### b) End-to-end with the Safaricom sandbox

Safaricom must be able to reach your machine, so a WSL laptop needs a temporary public HTTPS address. For sandbox testing only, Cloudflare Tunnel works well:

```bash
# in WSL, with bench start running
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cf.deb
sudo dpkg -i /tmp/cf.deb
cloudflared tunnel --url http://localhost:8000 --http-host-header school.localhost
```

It prints an address like `https://random-words.trycloudflare.com`. Make sure it doesn't contain a forbidden word, or rerun to get another. Then:

1. School Settings → Environment `Sandbox`, sandbox short code and keys, **Public Site URL** = that address → Save.
2. **Register URLs with Safaricom**.
3. **Simulate via Safaricom Sandbox** with a Student ID and amount.
4. Within seconds a new row appears in **Paybill Transactions** with status **Posted**.

### c) Production smoke test

After go-live and registering production URLs, have a staff member pay **KES 10** to the paybill with a real Student ID. Check: Paybill Transactions shows *Posted*, the student's balance dropped by 10, the parent SMS arrived. Then cancel that Fee Payment (the transaction becomes *Ignored*) or leave it as a credit.

---

## 4. Daily use for the bursar

* **Paybill Transactions** (School workspace → Fees) lists every paybill payment with its status:
  * **Posted**: done; links to the Fee Payment and the student.
  * **Unmatched**: account number didn't match a student. Open it, **Post to Student**, choose the child.
  * **Failed**: something blocked posting (e.g. the Mode of Payment has no account). The error is shown. Fix the cause, then **Post to Student**. Failed items are also retried automatically every hour (up to 5 times).
  * **Ignored**: its Fee Payment was cancelled. Post again only if it was cancelled by mistake.
* Payments go to the **oldest balance first**. If a parent wanted a specific fee (e.g. transport), cancel the auto-posted Fee Payment and re-enter it as "Specific fee types" with the same M-Pesa code. The cancelled transaction shows *Ignored*, and the code is reused on the new receipt.
* Overpayments become an advance (credit) and are used by the next term's invoice.
* A payment for a student the bursar already receipted by hand with the same M-Pesa code is linked, not posted twice.

## 5. Accounting

Each posted payment is: Fee Payment → Payment Entry (Receive), debit the M-Pesa Mode of Payment account, credit the student's receivable, allocated to their invoices. Reconcile the M-Pesa account against the paybill statement from the M-PESA org portal as usual. The `Paybill Balance After` field on each transaction helps.

## 6. If callbacks were missed

If the site was down and the response type was *Completed*, Safaricom accepted the payment but couldn't notify you. Find the payment in the M-PESA org portal statement, then create the **M-Pesa Transaction** by hand (M-Pesa code, amount, account number, date) and click **Post to Student**. The M-Pesa code check prevents double entry if the callback later arrives.

## 7. Security notes

* Safaricom callbacks are not signed. Protection comes from: HTTPS, the secret token in the URL, the optional IP allowlist, and the M-Pesa code being unique. Never share the callback URLs.
* To rotate the token (e.g. if a URL leaked): the *Callback Secret* field is read-only, so blank it from the bench console with `frappe.db.set_single_value("School Settings", "mpesa_callback_token", ""); frappe.db.commit()`, then save School Settings (a new one is generated) and click **Register URLs** again.
* For extra assurance on large schools, reconcile weekly against the org portal statement.
