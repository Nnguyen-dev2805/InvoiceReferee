"""Tests for the structure-generalization evaluation harness.

These assert the harness reads a provider-neutral manifest of recorded block
fixtures, runs the structure-aware extraction, and reports bounded metrics.
Expected values live only in the manifest; production code never reads them.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from verify.structure_harness import (
    load_manifest,
    load_case,
    run_case,
    run_all,
    summarize,
)

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures_structure" / "manifest.json"
RECORDED_DIR = MANIFEST_PATH.parent / "recorded"


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def results():
    return run_all()


def test_row_role_metric_ignores_unlabeled_but_correct_rows(results):
    """Only manifest-labeled rows are scored; unlabeled correct rows are neutral."""
    summary = summarize(results)
    assert summary.row_role_precision == pytest.approx(1.0)
    assert summary.row_role_recall == pytest.approx(1.0)


def test_set_overlap_returns_two_values_for_empty_expectations():
    """A fixture with no expected table rows must not crash the caller."""
    from verify.structure_harness import _set_overlap

    precision, recall = _set_overlap({("1:0:0", "DATA")}, set())
    assert (precision, recall) == (1.0, 1.0)


def test_every_layout_family_has_two_distinct_cases(manifest):
    """Two cases per family must be genuinely different documents, not clones."""
    by_family: dict[str, list[str]] = {}
    for cid, case in manifest.items():
        by_family.setdefault(case["family"], []).append(cid)
    for family, ids in by_family.items():
        assert len(ids) == 2, f"{family} should have exactly 2 cases"
        docs = []
        for cid in ids:
            raw = json.loads((RECORDED_DIR / f"{cid}.json").read_text(encoding="utf-8"))
            raw.pop("document_id", None)
            docs.append(json.dumps(raw, sort_keys=True))
        assert docs[0] != docs[1], f"{family} variants are byte-identical"


def test_every_layout_family_has_two_cases(manifest):
    counts = Counter(case["family"] for case in manifest.values())
    assert set(counts.values()) == {2}
    assert len(manifest) == 20


def test_recorded_geometry_preserves_page_positions():
    document = load_case("ST01")
    series = next(b for b in document.blocks if b.block_id == "SER")
    assert series.bounding_box.x1 == pytest.approx(0.05)
    assert series.bounding_box.y1 == pytest.approx(0.08)


@pytest.mark.parametrize("case_id", ["ST07", "ST08"])
def test_label_above_value_fixture_has_separate_nonoverlapping_blocks(case_id):
    blocks = {b.block_id: b for b in load_case(case_id).blocks}
    assert {"TAX-L", "TAX-V"} <= blocks.keys()
    label, value = blocks["TAX-L"], blocks["TAX-V"]
    assert label.text == "Mã số thuế:"
    assert value.text == "0110329220"
    assert label.bounding_box.y2 < value.bounding_box.y1
    assert label.bounding_box.x1 == value.bounding_box.x1


def test_harness_reports_zero_false_auto_confirms(results):
    summary = summarize(results)
    assert summary.false_auto_confirm_count == 0


def test_harness_requires_provenance_for_selected_fields(results):
    for r in results:
        assert r.provenance_ok, f"{r.case_id} missing provenance"


def test_provenance_gate_covers_line_items_too():
    """A valued line-item candidate with no evidence blocks must fail the gate."""
    from verify import structure_harness

    case_id = next(iter(load_manifest()))
    document = load_case(case_id)
    result = structure_harness.extract_invoice_fields(document)
    assert result.line_items, f"{case_id} should yield line items"
    first = next(iter(result.line_items[0].values()))
    first.evidence_block_ids = []
    assert not structure_harness._provenance_ok(result)


def test_reports_field_recall_and_normalized_exact_match(results):
    summary = summarize(results)
    assert summary.field_recall == pytest.approx(1.0)
    assert summary.normalized_exact_match == pytest.approx(1.0)


def test_reports_line_item_precision_and_recall(results):
    summary = summarize(results)
    assert summary.line_item_precision == pytest.approx(1.0)
    assert summary.line_item_recall == pytest.approx(1.0)


def test_a_jpg_family_is_in_manifest(manifest):
    a_jpg_cases = [cid for cid, case in manifest.items() if case["family"] == "TABLE_FOOTER_TOTAL"]
    assert a_jpg_cases


def test_manifest_is_never_read_by_production_code():
    """Production must not import the manifest; grep the src tree for it."""
    import subprocess
    src = Path(__file__).resolve().parent.parent / "src"
    out = subprocess.run(
        ["grep", "-rn", "manifest", str(src)],
        capture_output=True, text=True,
    )
    # No production file references the structure manifest.
    assert "fixtures_structure" not in out.stdout
