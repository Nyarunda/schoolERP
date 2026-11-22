# Schools with several branches: requirements

*Branch: `feat/school-groups` · Roadmap item: #15 · Status: Agreed*

Owner (22 Nov): "if one school has many branches how do we handle that from domain, management of everything" → chose
**a separate site for each branch, grouped in the Control Center**, "plus I see cost center and projects in frappe".
Choices: billing **chosen per group** (one combined bill or each branch separately); **a cost center per school**, a
group's branches under the group's cost center; projects not used.

## Must
1. **SaaS School Group**: name, billing (One combined bill / Each branch billed separately), head office billing email and
   phone, notes. Schools get **School Group** and **Branch**. Each branch keeps its own site and domain
   (e.g. `greenhills-kisii.stemicschools.com`), licence and subscription.
2. **Cost centers** (Stemic's books): every school has one ("<school> - <branch> (<id>)"), under "Group - <group>" for a
   group's branches, else under "Schools"; moved when a school joins or leaves a group. Invoices (income, VAT), payments,
   commissions, credit notes, refunds and expenses for a school post with its cost center → Profit and Loss by school,
   branch and group (ERPNext cost-center filters and the cost-center tree).
3. **Combined bill**: each branch still has its own invoice (licences and balances stay right), but invoice, payment,
   overdue and trial-ending emails go to the head office; **Email Statement** sends one statement of all branches' open
   invoices; **Record Group Payment** spreads one payment over the branches' invoices oldest first (references /1, /2…).
4. Group form: branches with site, status, plan and what each owes, and the group total; Add Branch; New Branch Site.
   Sidebar: Schools > **School Groups**.

## Must not
- No shared data between branch sites (each is its own site); no change for schools without a group.
- Entries posted before this keep the company's default cost center (not re-posted).
