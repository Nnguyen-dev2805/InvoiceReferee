"""Independent fixtures for the settlement rule engine (W02).

Builders construct observations/relations/run inputs directly from scenario
semantics; they never call the engine under test to produce expected values.
Fact-key vocabulary mirrors the contract documented in ``settlement/rules.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pathlib import Path

from invoice_referee.settlement.models import (
    Observation,
    Relation,
    RunInput,
    SourceRecord,
    Submission,
)

_CUTOFF = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)


def submission(job: str = "B7", work_ref: str = "CT-01") -> Submission:
    return Submission(employee_ref="NV-01", work_ref=work_ref, job=job,
                      money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                      form={"purpose": "Công tác A"})


def fact(fact_id: str, key: str, value, source_id: str = "S1",
         read_state: str = "READ", basis: str | None = None) -> Observation:
    return Observation(
        fact_id=fact_id, key=key,
        raw=None if value is None else str(value),
        read_state=read_state,  # type: ignore[arg-type]
        value=value, source_id=source_id,
        basis=basis or "structured ledger fixture",
    )


def unclear_fact(fact_id: str, key: str, source_id: str = "S1") -> Observation:
    return Observation(fact_id=fact_id, key=key, raw="số bị mờ",
                       read_state="UNCLEAR", value=None, source_id=source_id,
                       basis="trích thức mờ không đọc được")


def expense_facts(expense_id: str, amount, purpose: str = "BUSINESS",
                  source_id: str = "S1") -> list[Observation]:
    facts = [fact(f"{expense_id}-amount", f"expense.{expense_id}.amount",
                  amount, source_id)]
    if purpose is not None:
        facts.append(fact(f"{expense_id}-purpose", f"expense.{expense_id}.purpose",
                          purpose, source_id))
    return facts


def payment_facts(payment_id: str, amount, payer: str = "EMPLOYEE",
                  status: str = "RECEIVED", source_id: str = "S2") -> list[Observation]:
    return [
        fact(f"{payment_id}-amount", f"payment.{payment_id}.amount", amount, source_id),
        fact(f"{payment_id}-payer", f"payment.{payment_id}.payer", payer, source_id),
        fact(f"{payment_id}-status", f"payment.{payment_id}.status", status, source_id),
    ]


def history_facts(a=None, ra=None, p=None, rp=None,
                  source_id: str = "S3") -> list[Observation]:
    facts: list[Observation] = []
    for name, value in (("received", a), ("returned", ra)):
        if value is not None:
            facts.append(fact(f"adv-{name}", f"history.advance.{name}",
                              value, source_id))
    for name, value in (("received", p), ("returned", rp)):
        if value is not None:
            facts.append(fact(f"reimb-{name}", f"history.reimbursement.{name}",
                              value, source_id))
    return facts


def budget_fact(amount, source_id: str = "S4") -> Observation:
    return fact("budget-approved", "budget.approved", amount, source_id)


def expense_payment(rel_id: str, expense_id: str, payment_id: str,
                    portion=None, refs: tuple[str, ...] = ("S1", "S2")) -> Relation:
    return Relation(relation_id=rel_id, kind="EXPENSE_PAYMENT",
                    from_id=expense_id, to_id=payment_id,
                    portion_vnd=portion, supporting_refs=list(refs),
                    status="ESTABLISHED",
                    reason="structured ledger: payment settles expense part")


def same_event(rel_id: str, first: str, second: str,
               refs: tuple[str, ...] = ("S2",)) -> Relation:
    return Relation(relation_id=rel_id, kind="SAME_EVENT",
                    from_id=first, to_id=second, portion_vnd=None,
                    supporting_refs=list(refs), status="ESTABLISHED",
                    reason="structured ledger: hai bản ghi cùng một giao dịch")


def run_input(job: str = "B7", facts=(), relations=(),
              max_settlement: int = 100_000_000,
              work_ref: str = "CT-01") -> RunInput:
    """Build a RunInput plus the engine inputs; sources referenced by fixtures."""
    from invoice_referee.settlement.models import AuthorityGrant

    return RunInput(
        case_id="C-TEST", case_version=1, input_revision=1, control_epoch=1,
        submission=submission(job, work_ref),
        sources=[_source_record(f"S{i}") for i in range(1, 5)],
        coverage=None, policy={"version": "demo-v0", "activated": True},
        authority=[AuthorityGrant(actor_ref="P-01", work_ref=None,
                                  max_settlement_vnd=max_settlement)],
        response_refs=[], config={"reader_mode": "FAKE_OR_REPLAY"},
        snapshot_hash="snap-test",
    ), list(facts), list(relations)


def _source_record(source_id: str) -> SourceRecord:
    return SourceRecord(
        id=source_id, case_id="C-TEST", filename=f"{source_id}.txt",
        media_type="text/plain", sha256=f"hash-{source_id}", size_bytes=64,
        status="ACCEPTED", uploader_actor_id="NV-01", received_at=_CUTOFF,
        provenance={}, original_path=Path(f"{source_id}.txt"),
    )
