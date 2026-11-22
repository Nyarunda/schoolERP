# School website: requirements

*Branch: `feat/school-website` · Roadmap item: #16 · Status: Agreed (design approved 22 Nov 2026)*

## Why

The owner, opening mogongapagsecondary.stemicschools.com: "check how to can improve this, looks soo basic and not
professional enough". Today the school's address opens Frappe's stock sign-in card with a small Stemic logo. Parents
and visitors get no school name, crest, fees details or contacts. The status pages are plain cards, and the suspended
page shows the school's unpaid Stemic invoice to every parent. The owner approved the design on the canvas
"School website redesign" ("the design i good implement").

## Who uses it

| Role | What they do with it |
|---|---|
| Parent / visitor (not signed in) | Opens the school's address and sees a homepage branded for the school. They can find how to pay fees, term dates, notices and contacts, apply for admission, check a document or raise a concern. |
| Parent (signed in) | Goes from the homepage to **My children** (the parent portal). |
| Staff | Signs in from the branded sign-in page and goes to the desk. |
| School admin | Fills in the website details in **School Settings › Website**, and ticks **Show on the school website** on a notice. |
| Stemic | Suspends a school. Parents then see a calm "portal paused" page with the school's own contacts. The reasons and the amount due sit under "For school administrators". |

## Must

1. **Homepage at "/"**. It is branded with the school's name, crest (or initials), motto, colour and photos. It has:
   - six action cards: Parent portal, Apply for admission, How to pay fees, Verify a document, Staff sign in,
     Contact or raise a concern;
   - a fees panel showing the Paybill and account (or Till) and the bank details;
   - notices, term dates for the current school year, a document-check box, an About section, contacts with a
     directions link, and a footer with a small "Powered by Stemic Schools".
2. Cards for modules the school has not licensed, or has switched off, are hidden. Parent portal needs the portal
   module with **Parent portal on**. Apply needs the admissions module with **Accepting applications**. Complaints
   need the welfare module. Sections with no data (no notices, no terms, no Paybill) are left out rather than shown
   empty.
3. A school admin can switch the homepage off (**Show the school homepage**). "/" then opens the sign-in page as it
   does today.
4. Signed in, the header button says **My children** for parents and **Open the school system** for staff, in place
   of **Sign in**.
5. **Branded sign-in**: the school's colour, crest, name and photo on one side and the sign-in form on the other.
   On a phone the brand becomes a top band. It includes a note for parents: sign in with the phone number
   you gave the school and the password sent by SMS, and ask the office for a new one if it is lost. (Forgot password
   needs an email address, which phone-only parents do not have.) All of Frappe's sign-in features keep working: password, forgot
   password, email link and social logins.
6. **One header and footer** on the school's public pages: homepage, admission status, complaint status, verify. The
   standard Frappe navbar (parent portal, web forms) shows the school's crest and name instead of "Home".
7. **Portal paused page** (suspension):
   - It shows the school's crest, name and colour, and says "The school portal is paused for now" and that records
     are safe.
   - It gives the school office phone and email.
   - Stemic's reason, amount due, how to pay, contacts and **Check again** move into a "For school administrators"
     section, closed by default.
   - It never needs the database to render. If it cannot read the school's settings, it still shows Stemic's
     details.
8. **Notices on the website**: a **Show on the school website** tick on School Notice. The homepage shows up to three
   published, unexpired notices with that tick, pinned ones first.
9. It works at phone width: the menu folds away, cards stack, and the tables fit.

## Must not / out of scope

- No new licensed module: the website is part of core and every school gets it.
- No change to who can sign in, or how.
- No public listing of staff-only notices: only notices with the website tick appear.
- No embedded map (it needs a Google API key). A **Get directions** link opens the school's map link.
- Web forms (Apply, Complaint) keep Frappe's form layout. They get the branded navbar only.
- No page editor: content comes from School Settings fields.

## Rules and permissions

- Guests can read only what the homepage shows: the School Settings website fields, terms, and notices ticked for
  the website. They read nothing through the API that they cannot read today. The page builds its data on the
  server.
- Writing: School Settings and School Notice keep their current permissions.

## Open questions

- None. The map embed and a full notices page can follow if schools ask.
