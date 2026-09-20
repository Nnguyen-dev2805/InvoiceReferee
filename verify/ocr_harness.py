"""OCR extraction evaluation harness (test/evaluation only).

Loads the synthetic OCR evaluation set, runs each document through the
production extraction pipeline using a recorded OCR response (deterministic) or
the live local model (``--live-ocr``), applies the manifest's field-review spec,
converts to canonical evidence, runs the production ``review()``, and reports
per-field exact-match metrics plus safety metrics.

Ground-truth expected values live only in the manifest, which production code
never reads. This module is imported by tests and run as a CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion import normalization as norm
from invoice_referee.ingestion.ocr import map_paddle_response
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields
from invoice_referee.ingestion.identity_resolution import resolve_invoice_identities
from invoice_referee.ingestion.extraction_validation import validate_extraction
from invoice_referee.ingestion.document_router import render_document
from invoice_referee.ingestion.image_preprocessing import preprocess_pages
from invoice_referee.ingestion.file_validation import validate_upload
from invoice_referee.ingestion.pipeline import (
    FieldReview,
    apply_field_reviews,
    reviewed_invoice_to_evidence,
)
from invoice_referee.services.reviewer import review
from invoice_referee.audit.store import AuditStore

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures_ocr"
GENERATED_DIR = FIXTURES_DIR / "generated"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


@dataclass(frozen=True)
class OCRCase:
    case_id: str
    filename: str
    mime_type: str
    kind: str
    path: Path
    recorded_ocr: dict
    base_evidence: dict
    field_review_spec: dict
    expected: dict[str, Any]
    expected_action: str
    invoice_id_key: str


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_ocr_case(case_id: str) -> OCRCase:
    raw = load_manifest()[case_id]
    return OCRCase(
        case_id=case_id,
        filename=raw["file"],
        mime_type=raw["mime_type"],
        kind=raw["kind"],
        path=GENERATED_DIR / raw["file"],
        recorded_ocr=json.loads((FIXTURES_DIR / raw["recorded_ocr"]).read_text(encoding="utf-8")),
        base_evidence=raw["base_evidence"],
        field_review_spec=raw["field_reviews"],
        expected=raw["expected"],
        expected_action=raw["expected_action"],
        invoice_id_key=raw["invoice_id_key"],
    )


class RecordedOCREngine:
    """An OCREngine that replays a recorded provider-neutral response."""

    def __init__(self, recorded: dict):
        self.recorded = recorded

    def analyze(self, pages: list[m.DocumentPage]) -> m.OCRDocument:
        blocks = map_paddle_response(self.recorded, pages)
        return m.OCRDocument(
            document_id=pages[0].document_id,
            pages=pages,
            blocks=blocks,
            full_text="\n".join(b.text for b in blocks),
            engine="recorded-paddleocr",
            engine_version="fixture-v1",
            processing_ms=0,
            warnings=[],
        )


def build_field_reviews(spec: dict, result: m.InvoiceExtractionResult) -> dict[str, FieldReview]:
    """Turn a manifest review spec into FieldReview commands (no production read).

    ``CONFIRM_ALL`` confirms every extracted critical header/line field; explicit
    ``overrides`` (keyed by field name) apply CORRECT or MARK_UNKNOWN.
    """
    overrides = spec.get("overrides", {})
    reviews: dict[str, FieldReview] = {}

    if spec.get("mode") == "CONFIRM_ALL":
        for name in result.fields:
            reviews[name] = FieldReview.confirm()
        for index, line in enumerate(result.line_items):
            for name in line:
                reviews[f"line_items[{index}].{name}"] = FieldReview.confirm()

    for name, ov in overrides.items():
        action = ov["action"]
        if action == "CORRECT":
            reviews[name] = FieldReview.correct(ov["value"], reason=ov.get("reason", "correction"))
        elif action == "MARK_UNKNOWN":
            reviews[name] = FieldReview.mark_unknown(ov.get("reason", "unreadable"))
        else:
            reviews[name] = FieldReview.confirm()

    return reviews


def _extract(case: OCRCase, *, live: bool) -> tuple[m.InvoiceExtractionResult, AuditStore, float]:
    po = norm.to_purchase_order(case.base_evidence["purchase_order"])
    document = validate_upload(case.filename, case.mime_type, case.path.read_bytes())
    audit = AuditStore(transaction_id=case.base_evidence["transaction_id"])
    audit.record_document_uploaded(document)
    audit.record_document_validated(document)
    pages = preprocess_pages(render_document(document))

    started = time.perf_counter()
    if live:
        from invoice_referee.ingestion.ocr import PaddleOCREngine

        engine = PaddleOCREngine()
    else:
        engine = RecordedOCREngine(case.recorded_ocr)
    ocr_document = engine.analyze(pages)
    elapsed = time.perf_counter() - started

    audit.record_ocr_completed(ocr_document)
    result = extract_invoice_fields(ocr_document)
    result = resolve_invoice_identities(result, po)
    result = validate_extraction(result)
    return result, audit, elapsed


@dataclass
class CaseResult:
    case_id: str
    kind: str
    field_matches: dict[str, bool]
    decision_action: str
    expected_action: str
    action_pass: bool
    false_auto_confirm: bool
    provenance_ok: bool
    latency_s: float


def run_case(case_id: str, *, live: bool = False) -> CaseResult:
    case = load_ocr_case(case_id)
    result, audit, elapsed = _extract(case, live=live)

    reviews = build_field_reviews(case.field_review_spec, result)
    reviewed = apply_field_reviews(result, reviews, actor="eval")
    audit.record_extraction_reviewed(reviewed, actor="eval")

    evidence = reviewed_invoice_to_evidence(reviewed, case.base_evidence)
    # Keep payment history pointing at the resolved internal invoice id.
    for rec in evidence.get("payment_history", []):
        rec["invoice_id"] = evidence["invoice"]["invoice_id"]
    review_result = review(evidence, audit=audit)

    field_matches = {}
    for name, expected_value in case.expected.items():
        cand = reviewed.fields.get(name)
        actual = cand.normalized_value if cand else None
        field_matches[name] = actual == expected_value

    # False auto-confirm: a critical field confirmed as EXTRACTED/CONFIRMED but
    # whose value does not match ground truth.
    false_auto_confirm = False
    for name, matched in field_matches.items():
        cand = reviewed.fields.get(name)
        if cand and cand.status in (m.FieldStatus.CONFIRMED, m.FieldStatus.EXTRACTED) and not matched:
            if case.field_review_spec.get("overrides", {}).get(name) is None:
                false_auto_confirm = True

    provenance_ok = _provenance_ok(reviewed)

    return CaseResult(
        case_id=case_id,
        kind=case.kind,
        field_matches=field_matches,
        decision_action=review_result.decision.action.value,
        expected_action=case.expected_action,
        action_pass=review_result.decision.action.value == case.expected_action,
        false_auto_confirm=false_auto_confirm,
        provenance_ok=provenance_ok,
        latency_s=elapsed,
    )


# Methods whose values come directly from OCR and therefore MUST cite blocks.
# Structural resolution (PO master / SKU map) and human edits legitimately have
# no OCR block provenance.
_OCR_DERIVED_METHODS = {"OCR_RULE", "OCR_TABLE", "NATIVE_PDF_TEXT", "LLM_ASSISTED"}


def _provenance_ok(result: m.InvoiceExtractionResult) -> bool:
    candidates = list(result.fields.values())
    for line in result.line_items:
        candidates.extend(line.values())
    for cand in candidates:
        if cand.extraction_method in _OCR_DERIVED_METHODS and cand.normalized_value is not None:
            if not cand.evidence_block_ids:
                return False
    return True


@dataclass
class Summary:
    document_count: int
    field_exact_match: float
    action_accuracy: float
    false_auto_confirm_count: int
    provenance_coverage: float
    p50_latency_s: float
    p95_latency_s: float
    results: list[CaseResult] = field(default_factory=list)


def summarize_results(results: list[CaseResult]) -> Summary:
    total_fields = sum(len(r.field_matches) for r in results)
    matched_fields = sum(sum(1 for v in r.field_matches.values() if v) for r in results)
    action_pass = sum(1 for r in results if r.action_pass)
    false_ac = sum(1 for r in results if r.false_auto_confirm)
    prov = sum(1 for r in results if r.provenance_ok)
    latencies = sorted(r.latency_s for r in results)

    def pct(sorted_vals, q):
        if not sorted_vals:
            return 0.0
        idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
        return sorted_vals[idx]

    n = len(results) or 1
    return Summary(
        document_count=len(results),
        field_exact_match=(matched_fields / total_fields) if total_fields else 1.0,
        action_accuracy=action_pass / n,
        false_auto_confirm_count=false_ac,
        provenance_coverage=prov / n,
        p50_latency_s=pct(latencies, 0.50),
        p95_latency_s=pct(latencies, 0.95),
        results=results,
    )


def run_all(*, live: bool = False) -> Summary:
    return summarize_results([run_case(cid, live=live) for cid in sorted(load_manifest())])


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OCR extraction evaluation harness")
    parser.add_argument("--live-ocr", action="store_true", help="run the local model instead of recorded responses")
    args = parser.parse_args(argv)

    summary = run_all(live=args.live_ocr)

    print(f"{'CASE':<8}{'KIND':<14}{'ACTION':<14}{'EXPECTED':<14}{'FIELDS':<10}{'PROV':<6}{'PASS'}")
    for r in summary.results:
        matched = sum(1 for v in r.field_matches.values() if v)
        fields = f"{matched}/{len(r.field_matches)}"
        print(
            f"{r.case_id:<8}{r.kind:<14}{r.decision_action:<14}{r.expected_action:<14}"
            f"{fields:<10}{'ok' if r.provenance_ok else 'MISS':<6}{'PASS' if r.action_pass else 'FAIL'}"
        )

    print()
    print(f"documents           : {summary.document_count}")
    print(f"field exact match   : {summary.field_exact_match:.1%}")
    print(f"action accuracy     : {summary.action_accuracy:.1%}")
    print(f"false auto-confirms : {summary.false_auto_confirm_count}")
    print(f"provenance coverage : {summary.provenance_coverage:.1%}")
    print(f"latency p50 / p95   : {summary.p50_latency_s*1000:.0f}ms / {summary.p95_latency_s*1000:.0f}ms")
    print(f"mode                : {'live-ocr' if args.live_ocr else 'recorded'}")

    ok = summary.false_auto_confirm_count == 0 and summary.action_accuracy == 1.0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
