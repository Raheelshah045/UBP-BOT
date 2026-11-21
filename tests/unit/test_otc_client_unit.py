"""Unit tests for OTC client classification, codes 95/98 exclusion, and bank resolution."""

from src.ubp_bot.portals.otc_client import (
    classify_transaction,
    resolve_bank_option_value,
)


def test_otc_code_95_strictly_excluded():
    """Verify that response code 95 is strictly excluded from qualifying rejections."""
    res = classify_transaction(status="REJECTED", response_code="95")
    assert res["is_qualifying_rejection"] is False
    assert res["classification"] == "Excluded Rejection"
    assert "95" in res["reason"]


def test_otc_code_98_strictly_excluded():
    """Verify that response code 98 is strictly excluded from qualifying rejections."""
    res = classify_transaction(status="DECLINED", response_code="98")
    assert res["is_qualifying_rejection"] is False
    assert res["classification"] == "Excluded Rejection"
    assert "98" in res["reason"]


def test_otc_approved_code_00_not_qualifying():
    """Verify that code 00 / Approved transactions are non-qualifying."""
    res = classify_transaction(status="SUCCESSFUL", response_code="00")
    assert res["is_qualifying_rejection"] is False
    assert res["classification"] == "Approved"


def test_otc_qualifying_rejection_code_51():
    """Verify that code 51 (Insufficient Funds) qualifies as a rejection."""
    res = classify_transaction(status="REJECTED", response_code="51")
    assert res["is_qualifying_rejection"] is True
    assert res["classification"] == "Rejected"


def test_otc_qualifying_rejection_code_05():
    """Verify that code 05 (Do Not Honor) qualifies as a rejection."""
    res = classify_transaction(status="DECLINED", response_code="05")
    assert res["is_qualifying_rejection"] is True
    assert res["classification"] == "Rejected"


def test_resolve_bank_option_value():
    """Verify bank dropdown value resolution."""
    available = {
        "UBL": "United Bank Limited (UBL)",
        "HBL": "Habib Bank Limited",
        "MCB": "MCB Bank Limited",
    }
    mapping = {"UBL": "United Bank Limited", "HBL": "Habib Bank Limited"}

    assert resolve_bank_option_value("UBL", mapping, available) == "UBL"
    assert resolve_bank_option_value("HBL", mapping, available) == "HBL"
    assert resolve_bank_option_value("Habib Bank Limited", mapping, available) == "HBL"
