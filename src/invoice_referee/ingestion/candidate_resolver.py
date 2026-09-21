"""Explicit resolution of competing field candidates.

Given all candidates produced for one field, pick a selected value by method
priority (never by provider confidence), merge provenance from candidates that
agree, and flag genuine disagreements as ``CONFLICTING`` instead of silently
choosing one. Every alternative is preserved for audit and human review.

Pure functions, standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from invoice_referee.domain import models as m

# Lower number = higher priority. Human always wins; exact deterministic methods
# outrank spatial, provider annotation, fuzzy, and LLM in that order.
METHOD_PRIORITY: dict[str, int] = {
    "HUMAN": 0,
    "EXACT_KEY_VALUE": 10,
    "SECTION_AWARE": 10,
    "TABLE_SUMMARY": 10,
    "TABLE_ITEM": 10,
    "NATIVE_PDF_TEXT": 10,
    "EXACT_SPATIAL": 20,
    "PROVIDER_ANNOTATION": 30,
    "FUZZY_SPATIAL": 40,
    "LLM_ASSISTED": 50,
    # Legacy method name from the pre-structure mapper.
    "OCR_RULE": 15,
    "OCR_TABLE": 15,
}

_UNKNOWN_PRIORITY = 100


@dataclass
class FieldResolution:
    field_name: str
    selected: Optional[m.FieldCandidate]
    alternatives: list[m.FieldCandidate] = field(default_factory=list)
    conflicting: bool = False


def _priority(candidate: m.FieldCandidate) -> int:
    return METHOD_PRIORITY.get(candidate.extraction_method, _UNKNOWN_PRIORITY)


def _has_value(candidate: m.FieldCandidate) -> bool:
    return candidate.normalized_value is not None


def resolve_field_candidates(
    field_name: str, candidates: list[m.FieldCandidate]
) -> FieldResolution:
    """Resolve competing candidates into one selected value plus alternatives."""
    if not candidates:
        return FieldResolution(field_name=field_name, selected=None)

    # Stable sort by method priority; original input order breaks ties.
    ordered = sorted(enumerate(candidates), key=lambda pair: (_priority(pair[1]), pair[0]))
    ordered_candidates = [c for _, c in ordered]

    # Select the first candidate that actually carries a value.
    selected = next((c for c in ordered_candidates if _has_value(c)), None)
    if selected is None:
        # No candidate produced a value; return the highest-priority one as-is.
        selected = ordered_candidates[0]
        alternatives = ordered_candidates[1:]
        return FieldResolution(field_name, selected, alternatives, conflicting=False)

    alternatives = [c for c in ordered_candidates if c is not selected]

    # Agreement vs conflict among *valued* candidates.
    valued_others = [c for c in alternatives if _has_value(c)]
    conflicting = any(c.normalized_value != selected.normalized_value for c in valued_others)

    # Merge evidence ids from candidates that agree on the value (order-stable,
    # no duplicates), without changing the selected method or scores.
    for other in valued_others:
        if other.normalized_value == selected.normalized_value:
            for block_id in other.evidence_block_ids:
                if block_id not in selected.evidence_block_ids:
                    selected.evidence_block_ids.append(block_id)

    if conflicting:
        selected.status = m.FieldStatus.CONFLICTING
        conflict_methods = sorted(
            {c.extraction_method for c in valued_others
             if c.normalized_value != selected.normalized_value}
        )
        warning = f"conflicting values from {', '.join(conflict_methods)}"
        if warning not in selected.warnings:
            selected.warnings.append(warning)

    return FieldResolution(field_name, selected, alternatives, conflicting)
