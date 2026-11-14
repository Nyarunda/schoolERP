"""Finance on ERPNext accounting, against a database: who gets access, supplier bills with VAT and withholding,
paying them, and the tax reports. bench --site <site> run-tests --module school_erp.tests.test_finance"""

import frappe
from frappe.utils import flt, nowdate

from school_erp.tests.test_integration import TestCase, setup_school
from school_erp.tests.test_tax import TAX_FIELDS


class TestFinance(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		from school_erp.api.tax import ensure_withholding_types
		from school_erp.setup.finance import setup_finance

		ensure_withholding_types()
		setup_finance()
		if not frappe.db.exists("Item", "School Service (test)"):
			frappe.get_doc({"doctype": "Item", "item_code": "School Service (test)", "item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
							"is_stock_item": 0, "stock_uom": "Nos"}).insert()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._saved = {f: frappe.db.get_single_value("School Settings", f) for f in TAX_FIELDS}

	def tearDown(self):
		frappe.set_user("Administrator")
		for f, v in self._saved.items():
			frappe.db.set_single_value("School Settings", f, v)
		frappe.clear_document_cache("School Settings", "School Settings")

	def configure(self, **values):
		s = frappe.get_doc("School Settings")
		s.update(values)
		s.save()
		frappe.clear_document_cache("School Settings", "School Settings")
		return frappe.get_doc("School Settings")

	def user(self, *roles):
		email = f"fin-{frappe.generate_hash(length=6)}@finance.test"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Fin", "send_welcome_email": 0,
						"roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
		return frappe.get_doc("User", email)

	def roles(self, user):
		return set(frappe.get_roles(user.name))

	# ------------------------------------------------------------------ access
	def test_school_finance_roles_open_erpnext_accounting(self):
		bursar = self.user("Bursar")
		self.assertTrue({"Accounts User", "Purchase Master Manager", "Sales Master Manager"} <= self.roles(bursar))
		self.assertNotIn("Accounts Manager", self.roles(bursar))
		admin = self.user("School Admin")
		self.assertIn("Accounts Manager", self.roles(admin))

		frappe.set_user(bursar.name)
		for doctype, ptype in (("Supplier", "create"), ("Customer", "create"), ("Purchase Invoice", "submit"),
							   ("Sales Invoice", "submit"), ("Payment Entry", "submit"), ("Bank Transaction", "create"),
							   ("Bank Reconciliation Tool", "read"), ("Bank Statement Import", "create"), ("Payment Reconciliation", "read")):
			self.assertTrue(frappe.has_permission(doctype, ptype), f"Bursar cannot {ptype} {doctype}")
		frappe.set_user("Administrator")

		# taking the school role away takes away what it granted, but not roles given another way
		bursar.reload()
		bursar.append("roles", {"role": "Accounts User"})  # already there: stays only while needed
		bursar.set("roles", [r for r in bursar.roles if r.role != "Bursar"])
		bursar.save(ignore_permissions=True)
		self.assertFalse({"Accounts User", "Purchase Master Manager"} & self.roles(bursar))

		teacher = self.user("Teacher", "Accounts User")  # given by hand, no school finance role
		teacher.append("roles", {"role": "Staff"})
		teacher.save(ignore_permissions=True)
		self.assertIn("Accounts User", self.roles(teacher))

	# ------------------------------------------------------------------ supplier bills
	def test_supplier_bill_with_vat_and_withholding_then_payment(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		s = self.configure(kra_pin="P051234567X", vat_registered=1, vat_rate=16, withhold_tax=1)
		self.assertTrue(frappe.db.exists("Tax Withholding Category", "Professional or Management Fees"))
		vat_template = frappe.db.get_value("Purchase Taxes and Charges Template", {"title": "Kenya Input VAT", "company": s.company})
		self.assertTrue(vat_template)

		supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": f"Auditors {frappe.generate_hash(length=4)}",
								   "supplier_group": frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0], "tax_id": "P051999999Z",
								   "tax_withholding_category": "Professional or Management Fees"}).insert()
		expense_account = frappe.db.get_value("Account", {"company": s.company, "root_type": "Expense", "is_group": 0})
		pi = frappe.get_doc({
			"doctype": "Purchase Invoice", "supplier": supplier.name, "company": s.company, "posting_date": nowdate(),
			"bill_no": "AUD-" + frappe.generate_hash(length=4), "apply_tds": 1, "taxes_and_charges": vat_template,
			"items": [{"item_code": "School Service (test)", "qty": 1, "rate": 10000, "expense_account": expense_account,
					   "cost_center": s.cost_center}],
		})
		pi.set_missing_values()
		pi.set_taxes()
		pi.insert()
		pi.submit()

		gl = {}
		for r in frappe.db.sql("""select account, sum(debit) d, sum(credit) c from `tabGL Entry`
			where voucher_no = %s and is_cancelled = 0 group by account""", pi.name, as_dict=True):
			gl[r.account] = (flt(r.d), flt(r.c))
		self.assertEqual(gl[s.input_vat_account], (1600, 0))  # claimable input VAT
		self.assertEqual(gl[s.wht_account], (0, 500))  # 5% withheld on the amount before VAT
		self.assertEqual(flt(pi.outstanding_amount), 11100)  # what the supplier is owed

		pe = get_payment_entry("Purchase Invoice", pi.name)
		pe.reference_no, pe.reference_date = "CHQ-1", nowdate()
		pe.insert()
		pe.submit()
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")), 0)

		from school_erp.school.report.vat_summary.vat_summary import execute as vat_summary
		from school_erp.school.report.withholding_tax_register.withholding_tax_register import execute as wht_register

		_c, rows, *_ = wht_register({"from_date": nowdate(), "to_date": nowdate()})
		row = next(r for r in rows if r.name == pi.name)
		self.assertEqual((row.voucher_type, row.supplier_pin, flt(row.taxable_value), flt(row.wht_amount)),
						 ("Purchase Invoice", "P051999999Z", 10000, 500))
		_c, months, *_ = vat_summary({"from_date": nowdate(), "to_date": nowdate()})
		self.assertGreaterEqual(flt(months[-1].purchases), 10000)
		self.assertGreaterEqual(flt(months[-1].input_vat), 1600)

	def test_withholding_rate_changes_reach_supplier_bills(self):
		self.configure(withhold_tax=1)
		wt = frappe.get_doc("Withholding Tax Type", "Contractual Fees")
		wt.rate = 4
		wt.save()
		rates = frappe.get_doc("Tax Withholding Category", "Contractual Fees").rates
		self.assertEqual(flt(rates[0].tax_withholding_rate), 4)
		wt.rate = 3
		wt.save()

	def test_finance_workspace_and_cards_are_installed(self):
		ws = frappe.get_doc("Workspace", "Finance")
		self.assertIn("Bank Reconciliation Tool", [l.link_to for l in ws.links])
		for card in ("Owed to Suppliers", "Paid to Suppliers This Month", "Owed by Other Customers", "Unreconciled Bank Lines"):
			self.assertTrue(frappe.db.exists("Number Card", card), card)

	# ------------------------------------------------------------------ students vs customers
	def test_students_and_normal_customers_are_kept_apart(self):
		from school_erp.setup.finance import CUSTOMER_GROUP, student_group

		self.assertEqual(frappe.db.get_single_value("Selling Settings", "customer_group"), CUSTOMER_GROUP)
		hall = frappe.get_doc({"doctype": "Customer", "customer_name": f"Church Hall Hire {frappe.generate_hash(length=4)}",
							   "customer_group": student_group()}).insert()  # put in the students group by mistake
		self.assertEqual(hall.customer_group, CUSTOMER_GROUP)

		student = frappe.get_doc({"doctype": "Student", "first_name": "apart", "last_name": "test", "stream": "Grade 4 Test",
								  "guardians": [{"guardian_name": "Grace Test", "relation": "Mother", "mobile_no": "0712345678"}]}).insert()
		self.assertEqual(frappe.db.get_value("Customer", student.customer, "customer_group"), student_group())

		s = frappe.get_doc("School Settings")
		income = frappe.db.get_value("Account", {"company": s.company, "root_type": "Income", "is_group": 0})
		for customer, amount in ((hall.name, 5000), (student.customer, 7000)):
			si = frappe.get_doc({"doctype": "Sales Invoice", "customer": customer, "company": s.company, "posting_date": nowdate(),
								 "due_date": nowdate(), "items": [{"item_code": "School Service (test)", "qty": 1, "rate": amount,
																   "income_account": income, "cost_center": s.cost_center}]})
			si.insert()
			si.submit()

		from school_erp.school.report.customer_balances.customer_balances import execute

		_c, rows, *_ = execute({"as_on": nowdate()})
		names = {r.customer for r in rows}
		self.assertIn(hall.name, names)
		self.assertNotIn(student.customer, names)  # students' balances are in Fee Balances
		self.assertEqual(flt(next(r for r in rows if r.customer == hall.name).outstanding), 5000)

		card = frappe.get_doc("Number Card", "Outstanding Fees")
		self.assertIn(["Sales Invoice", "student", "is", "set"], frappe.parse_json(card.filters_json))
