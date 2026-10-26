"""Fast structural tests for submission/issuance race-condition safeguards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_subscription_creation_serialized():
    code = (ROOT / "billing.py").read_text()
    assert "SELECT name FROM `tabSaaS Subscription` WHERE name = %s FOR UPDATE" in code
    assert "def validate_payment_for_submit" in code
    assert "SELECT name FROM `tabSaaS Invoice` WHERE name = %s AND docstatus = 1 FOR UPDATE" in code


def test_payment_submit_revalidates_live_balance():
    code = (ROOT / "stemic_control" / "doctype" / "saas_payment" / "saas_payment.py").read_text()
    assert "def before_submit(self):" in code
    assert "billing.validate_payment_for_submit(self)" in code


def test_ref_key_is_database_unique():
    import json
    schema = json.loads((ROOT / "stemic_control" / "doctype" / "saas_payment" / "saas_payment.json").read_text())
    field = next(row for row in schema["fields"] if row["fieldname"] == "reference_key")
    assert field["unique"] == 1
    assert 'hashlib.sha256(f"{doc.mode}|{doc.reference}".encode())' in (ROOT / "billing.py").read_text()
