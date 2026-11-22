# School website: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Homepage at "/" | `home_page` hook (Frappe `get_home_page`); a `www/` template page | `www/welcome.html` + `welcome.py`; `school_erp/website.py` builds the page data |
| Branding everywhere | `update_website_context` hook, the navbar's `brand_html` | `website.update_context` sets the crest + name and the favicon |
| Shared header/footer | Jinja includes | `templates/includes/school_site/{header,footer}.html`, `school_site.bundle.css` (hashed, so no year-long cache) |
| Branded sign-in | Frappe's `www/login.html` (later apps' `www` pages win) | `www/login.html` extends `frappe/www/login.html` and wraps `{{ super() }}` in the split layout; `www/login.py` calls Frappe's `get_context`, then adds the school data |
| Paused page | `before_request` (existing) | `suspension.page` redesigned; reads school name, logo, colour and contacts in a `try` |
| Website notices | School Notice | new Check `show_on_website` |
| Settings | School Settings single, `api/singles.get_settings` (defaults on old sites) | new **Website** tab |
| Colours readable | | `logic/website.readable(color)` darkens the school colour until white text passes 4.5:1 |

## Changes

| File | Change |
|---|---|
| `school_erp/logic/website.py` | Pure rules: `initials`, `readable`/`contrast`, `pay_steps` (Paybill vs Till), `excerpt` (strip HTML, cut), `terms_for_year` (pick the current year's terms) |
| `school_erp/website.py` | `site_info()` (name, crest, colour, contacts), `home_context()` (cards by licence, fees, notices, terms), `update_context(context)` for the hook |
| `school_erp/www/welcome.{html,py}` | The homepage; redirects to `/login` when switched off |
| `school_erp/www/login.{html,py}` | Branded sign-in |
| `school_erp/www/{admission-status,complaint-status,verify}.html` | Shared header/footer and styles |
| `school_erp/templates/includes/school_site/*.html` | Header, footer, crest macro |
| `school_erp/public/css/school_site.bundle.css` | Styles for the public pages |
| `school_erp/hooks.py` | `home_page = "welcome"`, `update_website_context` |
| `school_erp/suspension.py` | New paused page |
| `school_settings.json` | Website tab: `website_home_on` (default 1), `site_tagline`, `site_intro`, `site_about`, `site_photo`, `site_photo_2`, `site_color`, `office_hours`, `map_link`, `show_term_dates` (default 1) |
| `school_notice.json` | `show_on_website` |
| `tests/test_website_logic.py` | Unit tests (added to check.sh) |
| `tests/test_school_website.py` | Integration: homepage renders, licence hides cards, notices filter, switched-off redirect, sign-in page branded, navbar brand |
| `tests/test_suspension.py` | Updated for the new page |

## Data and migration

New fields only. Defaults reach existing schools through `get_settings` (website on, term dates on). No patch.

## Risks

- **Sign-in page.** Overriding it could break signing in.
  - Mitigations: the template extends Frappe's and keeps its form and script unchanged (`super()`), and the
    controller calls Frappe's own `get_context`. Integration tests render it and check the form is there.
- **Live schools see a new "/" at once.** Mogonga has not filled in the Website fields.
  - Mitigation: with nothing filled in, the page still looks finished (crest from initials, colour panel instead of a
    photo, empty sections hidden). Tell the owner to fill in the fields after deploy.
- **The suspension page renders on every request while a school is suspended.**
  - Mitigation: one cached single read, wrapped in `try`.

## Deploy notes

```bash
cd ~/frappe-bench/apps/school_erp && git pull upstream main
cd ~/frappe-bench && bench --site all backup --with-files
bench --site all migrate
bench build --app school_erp
bench --site all clear-cache          # also clears the cached home page per user
sudo supervisorctl restart all
```

Then fill in **School Settings › Website** on the test site (photo, colour, intro) and look at "/".
