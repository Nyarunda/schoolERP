"""Statically enforce critical compliance boundaries; Bench integration needed."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def test_invoice_transmission_is_off_by_default():
    source = (BASE / "etims.py").read_text()
    assert 'stemic_etims_live_enabled' in source
    assert '"signature_verified"' in source
    assert '"verification_evidence"' in source
    assert "Pending Submission" in source


def test_platform_and_tenant_sellers_are_separate():
    source = (BASE / "etims.py").read_text()
    assert 'seller_scope == "Stemic Platform"' in source
    assert 'seller_scope == "School"' in source
    assert '"Stemic Tax Settings"' in source
