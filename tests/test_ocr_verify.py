"""Tests for the OCR evaluation harness (recorded mode, requires ocr extra)."""

from __future__ import annotations

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

from verify import ocr_harness  # noqa: E402


@pytest.fixture(scope="module")
def summary():
    return ocr_harness.run_all(live=False)


def test_all_documents_processed(summary):
    assert summary.document_count == 15


def test_field_exact_match_is_perfect_on_recorded_set(summary):
    assert summary.field_exact_match == 1.0


def test_action_accuracy_is_perfect(summary):
    assert summary.action_accuracy == 1.0


def test_false_auto_confirm_rate_is_zero(summary):
    assert summary.false_auto_confirm_count == 0


def test_every_extracted_value_has_provenance(summary):
    assert summary.provenance_coverage == 1.0


def test_scenario_actions_match_expected():
    expected = {
        "OCR01": "AUTO_PROCESS",
        "OCR06": "REQUEST_INFO",
        "OCR07": "AUTO_PROCESS",
        "OCR08": "REQUEST_INFO",
        "OCR09": "ESCALATE",
        "OCR10": "REQUEST_INFO",
    }
    for cid, action in expected.items():
        result = ocr_harness.run_case(cid)
        assert result.decision_action == action, f"{cid} expected {action}, got {result.decision_action}"


def test_recorded_engine_needs_no_model():
    # The recorded path must not import paddleocr; run one case and check it works.
    result = ocr_harness.run_case("OCR01")
    assert result.action_pass
