"""Pure checks for verification reference and tampering safeguards."""
import re
import secrets


def test_verification_code_is_unguessable():
    code = secrets.token_urlsafe(32)
    assert len(code) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,100}", code)


def test_tampered_pdf_has_different_fingerprint():
    import hashlib
    issued = b"%PDF-1.4 receipt original"
    tampered = b"%PDF-1.4 receipt edited"
    assert hashlib.sha256(issued).digest() != hashlib.sha256(tampered).digest()
