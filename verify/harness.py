"""Verify harness — run documented cases through the production review() path.

One command runs a suite and prints a pass/fail table with a real timestamp.
The harness never re-implements decision logic; it calls the same ``review()``
service the UI uses, then compares the action against the manifest.

CLI:
    python -m verify.harness --suite core
    python -m verify.harness --suite escalation
    python -m verify.harness --suite all       # judge path, one action
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from invoice_referee.agent.llm_client import LLMClient
from invoice_referee.services.reviewer import review
from verify import manifest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@dataclass
class VerifyResult:
    case_id: str
    expected: str
    actual: str
    passed: bool
    uncertainty_type: Optional[str]
    question: Optional[str]
    target: Optional[str]
    fallback_used: bool
    timestamp: str
    suite: Optional[str] = None


def fixture_path(case_id: str) -> Path:
    return FIXTURES_DIR / f"{case_id}.json"


def load_case(case_id: str) -> dict[str, Any]:
    with open(fixture_path(case_id), encoding="utf-8") as f:
        return json.load(f)


def verify_evidence(
    case_id: str,
    evidence: dict[str, Any],
    expected: Optional[str] = None,
    client: Optional[LLMClient] = None,
    suite: Optional[str] = None,
) -> VerifyResult:
    result = review(evidence, client=client)
    decision = result.decision
    actual = decision.action.value
    exp = expected if expected is not None else manifest.EXPECTED.get(case_id, "")
    return VerifyResult(
        case_id=case_id,
        expected=exp,
        actual=actual,
        passed=(actual == exp),
        uncertainty_type=(decision.uncertainty.type.value if decision.uncertainty else None),
        question=decision.question,
        target=decision.target,
        fallback_used=result.agent_assessment.fallback_used if result.agent_assessment else False,
        timestamp=datetime.now(timezone.utc).isoformat(),
        suite=suite,
    )


def run_verify(
    case_ids: list[str], client: Optional[LLMClient] = None, suite: Optional[str] = None
) -> list[VerifyResult]:
    return [
        verify_evidence(cid, load_case(cid), client=client, suite=suite) for cid in case_ids
    ]


def run_suite(name: str, client: Optional[LLMClient] = None) -> list[VerifyResult]:
    if name == "all":
        results: list[VerifyResult] = []
        for suite_name in ("core", "escalation"):
            results.extend(run_verify(manifest.SUITES[suite_name], client=client, suite=suite_name))
        return results
    if name not in manifest.SUITES:
        raise ValueError(f"unknown suite '{name}'")
    return run_verify(manifest.SUITES[name], client=client, suite=name)


def _print_table(results: list[VerifyResult]) -> None:
    header = f"{'SUITE':<11} {'CASE':<6} {'EXPECTED':<13} {'ACTUAL':<13} {'RESULT':<6} {'UNCERTAINTY':<17} {'TARGET':<20} LLM"
    print(header)
    print("-" * len(header))
    for r in results:
        llm = "fallback" if r.fallback_used else "llm"
        print(
            f"{(r.suite or '-'):<11} {r.case_id:<6} {r.expected:<13} {r.actual:<13} "
            f"{('PASS' if r.passed else 'FAIL'):<6} {(r.uncertainty_type or '-'):<17} "
            f"{(r.target or '-'):<20} {llm}"
        )
        if r.question:
            print(f"            Q[{r.case_id}]: {r.question}")


def _summary(results: list[VerifyResult]) -> tuple[int, int]:
    passed = sum(1 for r in results if r.passed)
    return passed, len(results)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="InvoiceReferee Verify harness")
    parser.add_argument("--suite", choices=["core", "escalation", "all"], default="all")
    args = parser.parse_args(argv)

    results = run_suite(args.suite)
    print(f"InvoiceReferee Verify — suite '{args.suite}' @ {datetime.now(timezone.utc).isoformat()}\n")
    _print_table(results)
    passed, total = _summary(results)
    print(f"\n{passed}/{total} cases passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
