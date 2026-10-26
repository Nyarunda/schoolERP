"""Source-contract tests for report verification; full Frappe integration still required."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registry_requires_issuance_and_blocks_deletes():
    source = (ROOT / "school" / "doctype" / "verified_document" / "verified_document.py").read_text()
    assert "verification_issuance" in source
    assert "def before_insert" in source
    assert "def on_trash" in source


def test_issuer_role_separation_and_stamp_integrity():
    source = (ROOT / "api" / "document_verification.py").read_text()
    assert '"Fee Payment": {"School Admin", "System Manager", "Bursar"}' in source
    assert '"Report Card": {"School Admin", "System Manager", "Head Teacher"}' in source
    assert source.count("record.flags.verification_issuance = True") == 2
    assert "def _lock_source(" in source
    assert "FOR UPDATE" in source


def test_public_status_never_returns_private_data():
    source = (ROOT / "api" / "document_verification.py").read_text()
    endpoint = source.split("def verify(code=None):", 1)[1].split("def _issuer():", 1)[0]
    for secret in ('"file_url"', '"student"', '"amount"', '"pdf_hash"'):
        assert secret not in endpoint
