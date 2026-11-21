#!/usr/bin/env python3
"""Lay out the School sidebar (school_erp/school/sidebar/school/school.json) by LAYOUT below.

The existing link objects are moved, never rewritten, so their icons, filters and flags stay. It refuses to lose or
double a link: every link in the file must appear in LAYOUT exactly once, and every LAYOUT entry must exist.

  python scripts/regroup_sidebar.py          rewrite the file (bumps "modified")
  python scripts/regroup_sidebar.py --check  exit 1 if the file does not match LAYOUT (run by check.sh)

To add a link: add it to the JSON (any place), list it here, run the script.
"""

import copy
import json
import os
import sys
from datetime import datetime

PATH = os.path.join(os.path.dirname(__file__), "..", "school_erp", "school", "sidebar", "school", "school.json")

# A link is "Label|link_to". Sections: (label, icon, keep_closed, [links]). TOP: links above the first section.
TOP = ["Home|School", "Management Dashboard|management-dashboard", "Staff Room|staff-room", "Class Register|class-register",
       "Notice Board|School Notice", "Record Payment|Fee Payment"]
LAYOUT = [
    ("Students", "users", 0, [
        "Dashboard|Students and Welfare", "Active Students|Student", "Transferred Students|Student",
        "Graduated Students|Student", "All Students|Student", "Admission Applications|Admission Application",
        "Class Attendance|Class Attendance", "Stream|Stream", "Class|School Class", "Year-end Promotion|Student Promotion",
        "Certificates & Letters|School Certificate", "Verified Documents|Verified Document",
        "Class Enrolment|Class Enrolment", "NEMIS Census|NEMIS Census", "Admissions Pipeline|Admissions Pipeline",
        "Daily Attendance|Daily Attendance", "Attendance Register|Attendance Register"]),
    ("Welfare & Discipline", "heart-handshake", 0, [
        "Discipline Incident|Discipline Incident", "Complaint|Complaint", "Sick Bay Visit|Sick Bay Visit",
        "Health Records|Student Health Record", "Visitor Log|Visitor Log", "Gate Pass|Gate Pass",
        "Discipline Summary|Discipline Summary", "Complaints Summary|Complaints Summary",
        "Sick Bay Register|Sick Bay Register", "Visitor Register|Visitor Register"]),
    ("Boarding", "bed-double", 0, [
        "Dormitory|Dormitory", "Boarding Allocation|Boarding Allocation", "Exeat|Exeat",
        "Dormitory Occupancy|Dormitory Occupancy", "Exeat Register|Exeat Register"]),
    ("Academics", "book-open", 0, [
        "Timetable|Timetable", "Homework|Homework", "Subject|Subject", "Period|Period", "School Activity|School Activity",
        "Homework Register|Homework Register", "Teacher Workload|Teacher Workload"]),
    ("Exams & CBC", "award", 0, [
        "Exam|Exam", "Enter Marks|Exam Mark Sheet", "Marks to Approve|Exam Mark Sheet", "Report Card|Report Card",
        "Competency Assessment|Competency Assessment", "CBC Progress Report|CBC Progress Report",
        "CBC Strands|CBC Strand", "Grading Scale|Grading Scale", "Merit List|Exam Merit List",
        "Subject Analysis|Exam Subject Analysis", "CBC Summary|CBC Assessment Summary"]),
    ("Library", "library", 0, [
        "Library Books|Library Book", "Library Loans|Library Loan", "Library Overdue Books|Library Overdue Books",
        "Library Circulation|Library Circulation"]),
    ("Fees", "receipt", 0, [
        "Dashboard|Fees and Finance", "Fee Payment|Fee Payment", "Student Invoices|Sales Invoice",
        "Paybill Transactions|M-Pesa Transaction", "Portal Payments (STK)|STK Push Request",
        "Fee Billing Run|Fee Billing Run", "Fee Structure|School Fee Structure", "Fee Type|Fee Type",
        "Fee Balances|Fee Balances", "Fee Collection|Fee Collection", "Fee Structure Matrix|Fee Structure Matrix",
        "Paybill Reconciliation|Paybill Reconciliation"]),
    ("Pocket Money", "wallet", 0, [
        "Pocket Money|Pocket Money Account", "Pocket Money Transactions|Pocket Money Transaction",
        "Pocket Money Balances|Pocket Money Balances", "Pocket Money Statement|Pocket Money Statement"]),
    ("Finance", "landmark", 0, [
        "Dashboard|Finance", "Chart of Accounts|Account", "School Expense|School Expense", "Expense Category|Expense Category",
        "Suppliers|Supplier", "Supplier Bills|Purchase Invoice", "Customers|Customer",
        "Customer Invoices|Sales Invoice", "Payments|Payment Entry", "Bank Reconciliation|Bank Reconciliation Tool",
        "Journal Entry|Journal Entry", "Withholding Tax Types|Withholding Tax Type",
        "Income vs Expenses|Income vs Expenses", "Expense Register|Expense Register", "VAT Summary|VAT Summary",
        "Withholding Tax Register|Withholding Tax Register", "Customer Balances|Customer Balances"]),
    ("Staff", "id-card", 0, [
        "Dashboard|Staff", "Staff Member|Staff Member", "Teacher|Teacher", "Leave Application|Leave Application",
        "Leave Type|Leave Type", "Duty Roster|Duty Roster", "Duty Report|Duty Report", "Leave Balance|Leave Balance",
        "Staff On Leave|Staff On Leave", "Duty Reports Register|Duty Reports Register"]),
    ("Transport", "bus", 0, [
        "Dashboard|Transport", "Transport Route|Transport Route", "School Vehicle|School Vehicle",
        "Driver Daily Log|Driver Daily Log", "Transport List|Transport List",
        "Driver Check-in Register|Driver Check-in Register", "Vehicle Fuel and Mileage|Vehicle Fuel and Mileage"]),
    ("Parents & Messages", "message-square", 0, [
        "Parent Messages|School Message", "Parent Logins|User", "Parent Portal Access|Parent Portal Access"]),
    ("Accounts", "sheet", 1, [
        "Accounts Receivable|Accounts Receivable", "Accounts Payable|Accounts Payable", "General Ledger|General Ledger",
        "Trial Balance|Trial Balance", "Profit and Loss|Profit and Loss Statement", "Balance Sheet|Balance Sheet",
        "Cash Flow|Cash Flow", "Bank Reconciliation Statement|Bank Reconciliation Statement"]),
    ("Setup", "settings", 1, [
        "School Settings|School Settings", "School Year|School Year", "School Term|School Term",
        "Staff Users|User", "Job Roles|Role Profile", "Admission Settings|Admission Settings",
        "Library Settings|Library Settings", "CBC Settings|CBC Settings"]),
]

SECTION_TEMPLATE = {"added": 0, "child": 0, "collapsible": 1, "hidden": 0, "icon": "", "indent": 1,
                    "is_default_module": 0, "keep_closed": 0, "label": "", "link_type": "DocType", "open_in_new_tab": 0,
                    "show_arrow": 0, "type": "Section Break"}


def key(item):
    return f"{item.get('label')}|{item.get('link_to')}"


def build(doc):
    links = [i for i in doc["items"] if i.get("type") != "Section Break"]
    by_key = {}
    for i in links:
        if key(i) in by_key:
            sys.exit(f"Two links are both {key(i)}: remove one from the JSON first")
        by_key[key(i)] = i
    wanted = TOP + [k for _, _, _, ks in LAYOUT for k in ks]
    doubled = sorted({k for k in wanted if wanted.count(k) > 1})
    missing = sorted(set(wanted) - set(by_key))
    unplaced = sorted(set(by_key) - set(wanted))
    if doubled or missing or unplaced:
        sys.exit(f"Layout does not match the links. Twice in LAYOUT: {doubled}. Not in the JSON: {missing}. "
                 f"Not in LAYOUT: {unplaced}")
    items = []
    for k in TOP:
        items.append(dict(by_key[k], child=0, indent=0))
    for label, icon, closed, ks in LAYOUT:
        old = next((i for i in doc["items"] if i.get("type") == "Section Break" and i.get("label") == label), None)
        section = copy.deepcopy(old) if old else dict(SECTION_TEMPLATE)
        section.update(label=label, icon=icon, keep_closed=closed)
        items.append(section)
        for k in ks:
            items.append(dict(by_key[k], child=1))
    for n, i in enumerate(items):
        if "idx" in i:
            i["idx"] = n + 1
    return items


def layout_of(items):
    return [(i["type"], key(i), i.get("child", 0)) for i in items]


def main():
    with open(PATH) as f:
        raw = f.read()
    doc = json.loads(raw)
    items = build(doc)
    if "--check" in sys.argv:
        if layout_of(items) != layout_of(doc["items"]):
            sys.exit("The sidebar JSON does not follow scripts/regroup_sidebar.py: run it (without --check)")
        return
    doc["items"] = items
    doc["modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000000")
    indent = 1 if raw.startswith('{\n "') else 2
    with open(PATH, "w") as f:
        f.write(json.dumps(doc, indent=indent, ensure_ascii=False) + "\n")
    print(f"Sidebar regrouped: {len(LAYOUT)} sections, {sum(len(k) for *_, k in LAYOUT) + len(TOP)} links")


if __name__ == "__main__":
    main()
