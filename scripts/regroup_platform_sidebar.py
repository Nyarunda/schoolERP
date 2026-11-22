#!/usr/bin/env python3
"""Lay out the Control Center sidebar (platform/.../sidebar/stemic_control/stemic_control.json) by LAYOUT below, with the
same rules as scripts/regroup_sidebar.py (links are moved, never rewritten; none lost or doubled).

  python scripts/regroup_platform_sidebar.py          rewrite the file (bumps "modified")
  python scripts/regroup_platform_sidebar.py --check  exit 1 if the file does not match LAYOUT (run by check.sh)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import regroup_sidebar as base  # noqa: E402

base.PATH = os.path.join(os.path.dirname(__file__), "..", "platform", "stemic_control", "stemic_control", "stemic_control",
                         "sidebar", "stemic_control", "stemic_control.json")
base.TOP = ["Home|Stemic Control", "KPI Overview|stemic-overview"]
base.LAYOUT = [
    ("Schools", "school", 0, [
        "Dashboard|Schools", "All Schools|SaaS Tenant", "School Groups|SaaS School Group", "Domains|SaaS Domain", "Provisioning Jobs|SaaS Provisioning Job",
        "Deletions|SaaS Deletion"]),
    ("Billing", "receipt", 0, [
        "Dashboard|Billing", "Subscriptions|SaaS Subscription", "Invoices|SaaS Invoice", "Payments|SaaS Payment",
        "Credit Notes & Refunds|SaaS Credit Note",
        "Plans|SaaS Plan", "Licenses|SaaS License", "Revenue|SaaS Revenue", "What Schools Owe|SaaS Receivables"]),
    ("Agents", "users", 1, [
        "Dashboard|Agents", "All Agents|SaaS Agent", "Commissions|SaaS Commission",
        "Commission Statement|Agent Commission Statement"]),
    ("Expenses", "wallet", 1, [
        "Expenses|Stemic Expense", "Expense Categories|Stemic Expense Category", "Costs vs Revenue|Costs vs Revenue"]),
    ("Accounts", "sheet", 1, [
        "Chart of Accounts|Account", "Journal Entry|Journal Entry", "Sales Invoice|Sales Invoice", "Payment Entry|Payment Entry",
        "Bank Reconciliation|Bank Reconciliation Tool", "General Ledger|General Ledger", "Trial Balance|Trial Balance",
        "Profit and Loss|Profit and Loss Statement", "Balance Sheet|Balance Sheet", "Cash Flow|Cash Flow",
        "Accounts Receivable|Accounts Receivable", "Accounts Payable|Accounts Payable"]),
    ("Tax (eTIMS)", "file-check", 1, [
        "Tax Invoices|SaaS eTIMS Invoice", "Tax Profiles|SaaS Tax Profile", "Tax Settings|Stemic Tax Settings"]),
    ("Operations", "server", 1, [
        "Backups|SaaS Backup", "Site Operations|SaaS Site Operation", "Messages|SaaS Communication"]),
    ("Setup", "settings", 1, [
        "Settings & Setup Check|Stemic Settings", "Users|User", "Roles|Role"]),
]

if __name__ == "__main__":
    base.main()
