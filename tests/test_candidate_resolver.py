"""Tests for explicit candidate resolution (Task 3).

Candidates agree, merge provenance, or conflict. Provider confidence never
resolves a semantic disagreement; a lower-priority method never overwrites a
higher-priority one; conflicting values are preserved for human review.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.candidate_resolver import (
    FieldResolution,
    resolve_field_candidates,
)


def candidate(value, method, block_ids, *, confidence=0.99, field_name="total_amount",
              status=m.FieldStatus.EXTRACTED):
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=str(value),
        normalized_value=value,
        confidence=None,
        status=status,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=list(block_ids),
        extraction_method=method,
        provider_confidence=confidence,
    )


def test_empty_candidates_resolve_to_missing():
    resolution = resolve_field_candidates("total_amount", [])
    assert isinstance(resolution, FieldResolution)
    assert resolution.selected is None
    assert resolution.alternatives == []
    assert resolution.conflicting is False


def test_equal_values_merge_provenance_without_conflict():
    exact = candidate(9_000_000, "TABLE_SUMMARY", ["LABEL", "VALUE"])
    annotation = candidate(9_000_000, "PROVIDER_ANNOTATION", ["VALUE"])
    resolution = resolve_field_candidates("total_amount", [annotation, exact])
    assert resolution.conflicting is False
    assert resolution.selected.extraction_method == "TABLE_SUMMARY"
    assert resolution.selected.evidence_block_ids == ["LABEL", "VALUE"]
    assert resolution.alternatives == [annotation]


def test_agreeing_candidate_contributes_missing_evidence_ids():
    exact = candidate(9_000_000, "TABLE_SUMMARY", ["LABEL"])
    annotation = candidate(9_000_000, "PROVIDER_ANNOTATION", ["VALUE"])
    resolution = resolve_field_candidates("total_amount", [exact, annotation])
    # Selected keeps its method but gains the agreeing candidate's evidence id.
    assert resolution.selected.extraction_method == "TABLE_SUMMARY"
    assert resolution.selected.evidence_block_ids == ["LABEL", "VALUE"]
    assert resolution.conflicting is False


def test_different_values_are_conflicting_even_if_confidence_differs():
    high_conf_wrong = candidate(7_000_000, "PROVIDER_ANNOTATION", ["B1"], confidence=0.999)
    lower_conf_exact = candidate(9_000_000, "TABLE_SUMMARY", ["B2", "B3"], confidence=0.91)
    resolution = resolve_field_candidates("total_amount", [high_conf_wrong, lower_conf_exact])
    assert resolution.conflicting is True
    # Higher-priority method wins selection regardless of provider confidence.
    assert resolution.selected.normalized_value == 9_000_000
    assert resolution.selected.status is m.FieldStatus.CONFLICTING
    assert set(resolution.selected.evidence_block_ids) == {"B2", "B3"}
    assert resolution.alternatives == [high_conf_wrong]


def test_human_outranks_every_machine_method():
    human = candidate(5_000_000, "HUMAN", ["H"])
    exact = candidate(9_000_000, "TABLE_SUMMARY", ["S"])
    resolution = resolve_field_candidates("total_amount", [exact, human])
    assert resolution.selected.extraction_method == "HUMAN"
    assert resolution.selected.normalized_value == 5_000_000
    # A human decision plus a disagreeing machine value is still flagged.
    assert resolution.conflicting is True


def test_fuzzy_never_overwrites_exact_even_with_same_value():
    exact = candidate(9_000_000, "EXACT_KEY_VALUE", ["E"])
    fuzzy = candidate(9_000_000, "FUZZY_SPATIAL", ["F"])
    resolution = resolve_field_candidates("total_amount", [fuzzy, exact])
    assert resolution.selected.extraction_method == "EXACT_KEY_VALUE"


def test_candidate_with_no_value_is_not_selected_over_valued_one():
    empty = candidate(None, "EXACT_KEY_VALUE", ["E"])
    valued = candidate(9_000_000, "TABLE_SUMMARY", ["S"])
    resolution = resolve_field_candidates("total_amount", [empty, valued])
    assert resolution.selected.normalized_value == 9_000_000
