"""Kenya tax set up per school, against a database: VAT on fee invoices, VAT and withholding on supplier payments,
and the two monthly reports. bench --site <site> run-tests --module school_erp.tests.test_tax"""

import frappe
from frappe.utils import add_days, flt, nowdate

from school_erp.tests.test_integration import TestCase, setup_school

TAX_FIELDS = ("kra_pin", "vat_registered", "vat_rate", "output_vat_account", "input_vat_account", "withhold_tax",
			  "wht_account", "vat_withholding_agent", "vat_wht_rate", "vat_wht_account")


class TestTax(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		from school_erp.api.tax import ensure_withholding_types

		ensure_withholding_types()
		if not frappe.db.exists("Fee Type", "Uniform (tax test)"):
			frappe.get_doc({"doctype": "Fee Type", "fee_type_name": "Uniform (tax test)", "category": "Other",
							"charge_basis": "Once", "priority": 90, "vat_treatment": "Standard Rated"}).insert()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		self._saved = {f: frappe.db.get_single_value("School Settings", f) for f in TAX_FIELDS}

	def tearDown(self):
		for f, v in self._saved.items():
			frappe.db.set_single_value("School Settings", f, v)
		frappe.clear_document_cache("School Settings", "School Settings")

	def configure(self, **values):
		s = frappe.get_doc("School Settings")
		s.update(values)
		s.save()  # creates the tax accounts the settings call for
		frappe.clear_document_cache("School Settings", "School Settings")
		return frappe.get_doc("School Settings")

	def invoice(self, lines):
		from school_erp.api.billing import _fee_types, make_invoice

		student = frappe.get_doc({"doctype": "Student", "first_name": "tax", "last_name": "test", "stream": "Grade 4 Test",
								  "guardians": [{"guardian_name": "Grace Test", "relation": "Mother", "mobile_no": "0712345678"}]}).insert()
		rows = [{"fee_type": ft, "description": ft, "amount": amount, "discount_percent": 0} for ft, amount in lines]
		return make_invoice(student, self.term, rows, _fee_types(), nowdate(), add_days(nowdate(), 30))

	def expense(self, amount, **values):
		cat = frappe.get_all("Expense Category", filters={"is_active": 1}, limit=1, pluck="name")[0]
		return frappe.get_doc({"doctype": "School Expense", "expense_category": cat, "amount": amount, "payee": "Supplier",
							   "mode_of_payment": "_Test School Cash", "description": "tax test", **values}).insert()

	def supplier(self, pin="P051111111A"):
		name = "Tax Test Supplier"
		if not frappe.db.exists("Supplier", name):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": frappe.get_all("Supplier Group", pluck="name", limit=1)[0],
							"tax_id": pin}).insert()
		return name

	# ------------------------------------------------------------------ sales
	def test_not_registered_invoices_carry_no_vat(self):
		self.configure(vat_registered=0)
		si = self.invoice([("Tuition", 25000), ("Uniform (tax test)", 1160)])
		self.assertEqual((flt(si.grand_total), len(si.taxes)), (26160, 0))

	def test_registered_school_charges_vat_only_on_standard_rated_lines(self):
		s = self.configure(kra_pin="P051234567X", vat_registered=1, vat_rate=16)
		self.assertTrue(s.output_vat_account and s.input_vat_account)

		si = self.invoice([("Tuition", 25000), ("Uniform (tax test)", 1160)])
		self.assertEqual(flt(si.grand_total), 26160)  # parents pay the fee amounts: VAT is inside them
		self.assertEqual(flt(si.total_taxes_and_charges), 160)
		vat = frappe.db.get_value("GL Entry", {"voucher_no": si.name, "account": s.output_vat_account, "is_cancelled": 0}, "credit")
		self.assertEqual(flt(vat), 160)

		from school_erp.api.payments import invoice_fee_lines

		billed = {l["fee_type"]: l["billed"] for l in invoice_fee_lines([si.name])[si.name]["lines"]}
		self.assertEqual(billed, {"Tuition": 25000, "Uniform (tax test)": 1160})  # fee balances still add up

		exempt_only = self.invoice([("Tuition", 25000)])
		self.assertEqual(len(exempt_only.taxes), 0)

		from school_erp.school.report.vat_summary.vat_summary import execute

		_cols, data, *_ = execute({"from_date": nowdate(), "to_date": nowdate()})
		month = data[-1]
		self.assertGreaterEqual(flt(month.output_vat), 160)
		self.assertGreaterEqual(flt(month.standard), 1000)
		self.assertGreaterEqual(flt(month.exempt), 50000)

	def test_vat_registration_needs_a_valid_pin(self):
		self.assertRaises(frappe.ValidationError, self.configure, kra_pin="", vat_registered=1)
		self.assertRaises(frappe.ValidationError, self.configure, kra_pin="12345")

	# ------------------------------------------------------------------ purchases
	def test_supplier_payment_with_vat_and_withholding(self):
		from school_erp.api.expenses import make_journal_entry

		s = self.configure(kra_pin="P051234567X", vat_registered=1, vat_rate=16, withhold_tax=1,
						   vat_withholding_agent=1, vat_wht_rate=2)
		doc = self.expense(11600, supplier=self.supplier(), supplier_charged_vat=1,
						   withholding_tax_type="Professional or Management Fees")
		self.assertEqual((doc.vat_amount, doc.input_vat, doc.wht_amount, doc.vat_wht_amount, doc.amount_paid),
						 (1600, 1600, 500, 200, 10900))
		self.assertEqual(doc.supplier_pin, "P051111111A")

		je = frappe.get_doc("Journal Entry", make_journal_entry(doc))
		lines = {r.account: (flt(r.debit_in_account_currency), flt(r.credit_in_account_currency)) for r in je.accounts}
		self.assertEqual(lines[doc.expense_account], (10000, 0))
		self.assertEqual(lines[s.input_vat_account], (1600, 0))
		self.assertEqual(lines[s.wht_account], (0, 500))
		self.assertEqual(lines[s.vat_wht_account], (0, 200))
		self.assertEqual(flt(je.total_debit), 11600)

		doc.db_set({"docstatus": 1, "journal_entry": je.name})
		from school_erp.school.report.withholding_tax_register.withholding_tax_register import execute

		_cols, data, *_ = execute({"from_date": nowdate(), "to_date": nowdate()})
		row = next(r for r in data if r.name == doc.name)
		self.assertEqual((row.supplier_pin, flt(row.taxable_value), flt(row.wht_amount)), ("P051111111A", 10000, 500))

	def test_not_registered_school_pays_vat_as_cost(self):
		self.configure(vat_registered=0, withhold_tax=0, vat_withholding_agent=0)
		doc = self.expense(11600, supplier_charged_vat=1)
		self.assertEqual((doc.vat_amount, doc.input_vat, doc.amount_paid), (1600, 0, 11600))

	def test_withholding_needs_the_setting_and_a_supplier(self):
		self.configure(withhold_tax=0)
		self.assertRaises(frappe.ValidationError, self.expense, 5000, supplier=self.supplier(),
						  withholding_tax_type="Contractual Fees")
		self.configure(withhold_tax=1)
		self.assertRaises(frappe.ValidationError, self.expense, 5000, withholding_tax_type="Contractual Fees")
		self.assertEqual(self.expense(5000, supplier=self.supplier(), withholding_tax_type="Contractual Fees").wht_amount, 150)
