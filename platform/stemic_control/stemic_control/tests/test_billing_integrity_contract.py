"""Fast structural tests for submission/issuance race-condition safeguards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_subscription_creation_serialized():
    code = (ROOT / "billing.py").read_text()
    assert "SELECT name FROM `tabSaaS Subscription` WHERE name = %s FOR UPDATE" in code
    assert "def validate_payment_for_submit" in code
    assert "FROM `tabSaaS Invoice` WHERE name = %s FOR UPDATE" in code  # lock_invoice (it also reads docstatus)
    assert "FOR UPDATE" in code.split("def submitted_payments", 1)[1].split("def ", 1)[0]  # locking read of the balance
    assert "def lock_invoice(invoice):" in code


def test_payment_submit_revalidates_live_balance():
    code = (ROOT / "stemic_control" / "doctype" / "saas_payment" / "saas_payment.py").read_text()
    assert "def before_submit(self):" in code
    assert "billing.validate_payment_for_submit(self)" in code


def test_ref_key_is_database_unique():
    import json
    schema = json.loads((ROOT / "stemic_control" / "doctype" / "saas_payment" / "saas_payment.json").read_text())
    field = next(row for row in schema["fields"] if row["fieldname"] == "reference_key")
    assert field["unique"] == 1
    billing = (ROOT / "billing.py").read_text()
    assert "doc.reference_key = reference_key(doc.mode, doc.reference)" in billing
    assert 'hashlib.sha256(f"{mode}|' in billing.split("def reference_key", 1)[1].split("def ", 1)[0]


def test_cancellation_paths_use_same_invoice_lock():
    payment = (ROOT / "stemic_control" / "doctype" / "saas_payment" / "saas_payment.py").read_text()
    invoice = (ROOT / "stemic_control" / "doctype" / "saas_invoice" / "saas_invoice.py").read_text()
    assert "def before_cancel(self):" in payment
    assert "billing.lock_invoice(self.invoice)" in payment
    assert "billing.lock_invoice(self.name)" in invoice
