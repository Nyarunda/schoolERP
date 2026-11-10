# Server files: schools' own domains

A school can be reached at its own domain (for example `portal.greenhill.ac.ke` or `greenhill.stemic.cloud`) as well
as at `<school>.stemicschools.com`. The Control Center does everything except what needs root on the server; these
files do that part, once, and then keep it current without anyone editing nginx.

| File | Installed as | What it does |
|---|---|---|
| `nginx/stemic.conf` | `/etc/nginx/conf.d/stemic.conf` | The Control Center and every `<school>.stemicschools.com` (as before) |
| `nginx/stemic-site.conf` | `/etc/nginx/snippets/stemic-site.conf` | The settings every Stemic server block shares; serves the site folder `$stemic_site` |
| `stemic-domains-sync` | `/usr/local/sbin/stemic-domains-sync` | Control Center routes -> `/etc/nginx/conf.d/stemic-domains.conf` (the `$stemic_site` map and a server block per certificate), `nginx -t`, reload; the previous file is kept if nginx rejects the new one |
| `systemd/stemic-domains.path`, `.service` | `/etc/systemd/system/` | Run the sync whenever the Control Center changes `<bench>/config/stemic-domains.json` |

## Install (once)

```bash
sudo bash /home/frappe/frappe-bench/apps/stemic_control/server/install.sh /home/frappe/frappe-bench
```

It backs up the current nginx files to `/var/backups/stemic-nginx-<time>/` and puts them back if `nginx -t` fails.
Run it again after an update of these files.

## A certificate for each domain's zone

Cloudflare connects to this server in **Full (strict)** mode, so the server needs a certificate that covers the
hostname. For a zone in Stemic's Cloudflare account (for example `stemic.cloud`):

1. Cloudflare, that zone: **SSL/TLS > Origin Server > Create Certificate**, hostnames `stemic.cloud, *.stemic.cloud`.
2. Save it on the server as a pair with the same name (the key must stay private, never in Git or chat):

       sudo tee /etc/ssl/cloudflare/stemic.cloud.pem >/dev/null     # paste the certificate, Ctrl-D
       sudo tee /etc/ssl/cloudflare/stemic.cloud.key >/dev/null     # paste the private key, Ctrl-D
       sudo chmod 600 /etc/ssl/cloudflare/stemic.cloud.key
       sudo systemctl start stemic-domains.service                  # pick it up now

3. That zone: **SSL/TLS** mode **Full (strict)**.

The sync uses whichever certificate in `/etc/ssl/cloudflare` covers the hostname (`openssl x509 -checkhost`), so any
names work as long as `<name>.pem` and `<name>.key` go together.

A domain in a zone that is **not** in Stemic's Cloudflare account (a school's own `.ac.ke`) cannot get an Origin
Certificate from us, and the firewall only lets Cloudflare reach this server. Either the school delegates that
hostname to Stemic's Cloudflare, or Stemic sets up Cloudflare for SaaS (Custom Hostnames) on stemicschools.com.

## From the Control Center

1. **Claim** the domain on the school (Actions > Claim a Domain) and have the school publish the TXT record shown.
2. **Verify DNS.** The domain is then routed: the sync sets up nginx for it within seconds, if a certificate covers it.
3. **DNS for visitors:** a CNAME from the hostname to `stemicschools.com` (Proxied, the orange cloud).
4. **Check and Activate** on the domain. It puts a random file in the school's site and fetches it over
   `https://<domain>/`, so it passes only when DNS, Cloudflare, the certificate and the route all lead to this school.
   If not, it says what is missing. Verified domains are also checked every hour and activated when they pass.
5. **Make Primary** (optional): the school's password-reset links, portal links, receipts and the Control Center's
   emails use the domain from then on. **Disable** stops serving it and moves the links back to the school's subdomain.

What the sync did last: `/var/lib/stemic/domains-status.json` (shown on the domain's form), and
`journalctl -u stemic-domains`.
