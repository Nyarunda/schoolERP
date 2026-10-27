"""Static regression guards for C2B webhook receipt and posting safety.

These supplement, not replace, Frappe integration tests with real database/Redis.
"""
from pathlib import Path

PAYBILL = (Path(__file__).resolve().parents[1] / "api" / "paybill.py").read_text()


def test_ack_requires_persistent_storage():
    assert "if not hold_for_review(raw, problems):" in PAYBILL
    assert "return _json_response(pb.REJECT_OTHER, status=503)" in PAYBILL
    assert PAYBILL.index("frappe.db.commit()", PAYBILL.index("def record_confirmation")) < PAYBILL.index(
        "frappe.enqueue(", PAYBILL.index("def record_confirmation")
    )


def test_queue_failure_does_not_discard_received_record():
    source = PAYBILL.split("def record_confirmation", 1)[1].split("def post_transaction", 1)[0]
    assert "except Exception:" in source
    assert "job_id=f\"school-paybill-" in source
    assert "retry_pending()" in source


def test_untrusted_confirmations_cannot_auto_post():
    assert 'if tx.status in ("Posted", "Ignored", "Needs Review"):' in PAYBILL
    assert 'frappe.db.get_value("M-Pesa Transaction", name, "status") == "Needs Review"' in PAYBILL


def test_token_is_compared_in_constant_time():
    assert "secrets.compare_digest" in PAYBILL
