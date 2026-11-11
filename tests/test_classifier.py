"""Unit tests for transaction classification business logic."""

from src.classifier import classify_transaction


def test_approved_status_with_code_00_is_classified_as_approved() -> None:
    """Ensure that Approved status with response code 00 is classified as Approved."""
    result = classify_transaction("Approved", "00")
    assert result["classification"] == "Approved"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is False


def test_successful_status_with_code_00_is_classified_as_approved() -> None:
    """Ensure that Successful status with response code 00 is classified as Approved."""
    result = classify_transaction("Successful", "00")
    assert result["classification"] == "Approved"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is False


def test_rejected_status_with_code_95_is_classified_as_excluded_code_95() -> None:
    """Ensure that Rejected status with response code 95 is excluded from qualifying rejections."""
    result = classify_transaction("Rejected", "95")
    assert result["classification"] == "Excluded Code 95"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is True


def test_rejected_status_with_code_98_is_classified_as_excluded_code_98() -> None:
    """Ensure that Rejected status with response code 98 is excluded from qualifying rejections."""
    result = classify_transaction("Rejected", "98")
    assert result["classification"] == "Excluded Code 98"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is True


def test_rejected_status_with_code_51_is_classified_as_qualifying_rejection() -> None:
    """Ensure that Rejected status with other codes like 51 qualifies for rejection sheet."""
    result = classify_transaction("Rejected", "51")
    assert result["classification"] == "Rejected"
    assert result["is_qualifying_rejection"] is True
    assert result["is_exception"] is False


def test_rejected_status_with_code_05_is_classified_as_qualifying_rejection() -> None:
    """Ensure that Rejected status with code 05 qualifies for rejection sheet."""
    result = classify_transaction("Rejected", "05")
    assert result["classification"] == "Rejected"
    assert result["is_qualifying_rejection"] is True
    assert result["is_exception"] is False


def test_pending_status_with_any_code_is_classified_as_pending_exception() -> None:
    """Ensure that Pending transactions are routed to exceptions."""
    result = classify_transaction("Pending", "01")
    assert result["classification"] == "Pending"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is True


def test_unknown_status_and_code_combinations_are_routed_to_manual_review() -> None:
    """Ensure that ambiguous, conflicting or unknown statuses go to Manual Review."""
    result = classify_transaction("InReview", "99")
    assert result["classification"] == "Manual Review"
    assert result["is_qualifying_rejection"] is False
    assert result["is_exception"] is True
