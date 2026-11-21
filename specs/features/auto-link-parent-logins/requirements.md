# Auto-link parent logins: requirements

*Branch: `feat/auto-link-parent-logins` · Roadmap item: #2 · Status: Agreed*

## Why

On 14 Nov a parent (demo.parent@gmail.com) logged in and saw no children. The guardian rows had the email but no
login link (`Student Guardian.user`), because the login was created separately. The portal finds children only
through that link, and today only **Give Parents Portal Access** sets it. Forgetting the button leaves parents
with an empty portal.

## Who uses it

| Role | What they do with it |
|---|---|
| Bursar, School Admin, Secretary | Add or edit guardians on a student, or create a parent login by hand |
| Parent | Logs in and sees every child whose guardian row carries their email or phone |

## Must

1. Saving a Student links each guardian row with no login to an existing parent login whose email equals the
   guardian's email, or whose mobile number matches the guardian's phone (any of 0712…, 254712…, +254712…).
2. Creating or saving a parent login links it to every guardian row, on any student, with no login and the same
   email or phone.
3. Only **website logins** (parents) are linked, never staff accounts. A linked login gets the Parent role if it
   lacks it.
4. Works whatever order things happen in, and saving again changes nothing.

## Must not / out of scope

- Create logins or send passwords (still the Give Parents Portal Access button).
- Unlink or replace a link someone already set.
- Link when two different parent logins match the same guardian (ambiguous: left for the button or a person).

## Rules and permissions

Only when the school has the `portal` module. Runs as part of saving, with no extra permission needed. Parents still
see only students whose guardian row links their own login (`children_of`), and only active or suspended ones.

## Open questions

None.
