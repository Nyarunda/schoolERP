# Several platform domains: requirements

*Branch: `feat/platform-domains` · Roadmap item: #3 · Status: Agreed*

## Why

The owner (21 Nov): "as the school system grows… we need to add other domains as we onboard new schools, where/how to
have them in the system and choose which domain to use." One domain can already hold any number of schools (wildcard
DNS + wildcard certificate), so this is about **branding, country domains and spreading risk**, not capacity.

## Who uses it

| Role | What they do with it |
|---|---|
| Stemic platform admin | Lists Stemic's domains in Stemic Settings, picks the default, checks each is ready, picks a domain per new school |
| School | Is reached at `<school>.<chosen domain>`; its emails and links use that address |

## Must

1. **Stemic Settings → Platform Domains**: a list of domains, each **Enabled** or not, one **Default**. If the list
   is empty, today's single Platform Domain is the only domain (no change for existing installs).
2. **Check Domains** in Stemic Settings says, per domain, whether its wildcard DNS resolves and whether the server
   holds a certificate for it, in plain words with the fix.
3. **Onboard a School** shows a domain choice next to the address when more than one domain is enabled; the address
   check and reserved names (admin, www, api…) apply on the chosen domain.
4. A school's address on **any** of Stemic's domains is verified at once (no TXT record), like the default is today.
   Schools' own domains (`portal.school.ac.ke`) keep the TXT check.
5. The school remembers its domain (SaaS Tenant **Platform Domain**). Existing schools are set to today's domain.
6. A school on a non-default domain is routed by the server, checked live, and made its main address automatically
   once the live check passes; until then its links use its site address, which always works.
7. Disabling a domain stops it being offered for new schools; schools already on it keep working.

## Must not / out of scope

- Move existing schools to another domain (an operator can still claim and Make Primary by hand).
- Create DNS records or certificates (done by hand once per domain; see `server/README.md`).
- Change how a school's site folder is named.

## Rules and permissions

System Manager / Stemic Platform Admin only, as for every Control Center action.

## Open questions

None.
