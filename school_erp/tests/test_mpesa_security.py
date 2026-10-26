"""Pure unit tests for payment-envelope security; run with pytest."""
from school_erp.logic.paybill import confirmation_problems, valid_confirmation, valid_money, valid_stk_metadata


def test_paybill_requires_shortcode_transaction_and_positive_cents():
    valid = {"TransID": "ABC123", "BusinessShortCode": "600000", "TransAmount": "50.00"}
    assert valid_confirmation(valid, "600000")
    assert not valid_confirmation({**valid, "BusinessShortCode": "174379"}, "600000")
    assert not valid_confirmation({**valid, "TransID": ""}, "600000")
    assert valid_confirmation({**valid, "TransID": ""}, "600000", require_transaction_id=False)
    for amount in ("0", "-5", "nan", "Infinity", "10.999", "", None):
        assert not valid_confirmation({**valid, "TransAmount": amount}, "600000")


def test_money_validation():
    assert valid_money("1")
    assert valid_money("0.01")
    assert valid_money("120.50")
    assert not valid_money("0.001")
    assert not valid_money("1e999")


def test_stk_requires_actual_matching_receipt_amount_and_phone():
    valid = {"MpesaReceiptNumber": "UJP030FNA4", "Amount": 50, "PhoneNumber": 254708374149}
    assert valid_stk_metadata(valid, 50, "254708374149")
    assert not valid_stk_metadata({**valid, "Amount": 5}, 50, "254708374149")
    assert not valid_stk_metadata({**valid, "PhoneNumber": 254711111111}, 50, "254708374149")
    assert not valid_stk_metadata({**valid, "MpesaReceiptNumber": ""}, 50, "254708374149")
    assert not valid_stk_metadata({k: v for k, v in valid.items() if k != "Amount"}, 50, "254708374149")


def test_till_accepts_store_or_till_number():
    valid = {"TransID": "ABC123", "BusinessShortCode": "8812345", "TransAmount": "50.00"}
    assert valid_confirmation(valid, ["7712345", "8812345"])
    assert valid_confirmation({**valid, "BusinessShortCode": "7712345"}, ["7712345", "8812345"])
    assert not valid_confirmation({**valid, "BusinessShortCode": "600000"}, ["7712345", "8812345"])
    assert not valid_confirmation(valid, None)


def test_stk_phone_formats_match():
    meta = {"MpesaReceiptNumber": "UJP030FNA4", "Amount": 50, "PhoneNumber": 254708374149}
    for expected in ("0708374149", "+254 708 374 149", "254708374149"):
        assert valid_stk_metadata(meta, 50, expected), expected
    assert not valid_stk_metadata({**meta, "PhoneNumber": ""}, 50, "")


def test_problems_say_what_is_wrong():
    ok = {"TransID": "ABC123", "BusinessShortCode": "600000", "TransAmount": "50.00"}
    assert confirmation_problems(ok, "600000") == []
    bad = confirmation_problems({"TransID": "", "BusinessShortCode": "111", "TransAmount": "-1"}, "600000")
    assert len(bad) == 3 and "111" in bad[1] and "-1" in bad[2]
    assert confirmation_problems("junk", "600000") == ["Not a Daraja confirmation"]
