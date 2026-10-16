"""Activity dossier references survive the real context import/composition path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.config import Settings
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.runtime import build_workflow
from invoice_referee.workflow.db import Database

ROOT = Path(__file__).resolve().parents[2]
TYPED_CONTEXT = ROOT / "data/demo/tc01-company-context.json"
LEGACY_CONTEXT = ROOT / "tests/fixtures/legacy-company-context.json"
TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
TC01 = "activity:tc01"


def _context_file(
    tmp_path: Path,
    kind: str,
    references: list[str] | str | None,
    *,
    suffix: str,
) -> Path:
    source = TYPED_CONTEXT if kind == "typed" else LEGACY_CONTEXT
    payload = json.loads(source.read_text(encoding="utf-8"))
    if kind == "typed":
        activity = payload["activity"]
    else:
        activity = next(
            item for item in payload["activities"] if item["id"] == "activity:travel-a"
        )
    if references is None:
        activity.pop("references", None)
    else:
        activity["references"] = references
    path = tmp_path / f"{kind}-{suffix}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _compose(tmp_path: Path, db_path: Path, context_path: Path):
    return build_workflow(
        Settings(_env_file=None),
        "STUB",
        db=Database(db_path),
        uploads_dir=tmp_path / "uploads",
        context_path=context_path,
    )


def _activity_id(kind: str) -> str:
    return TC01 if kind == "typed" else "activity:travel-a"


def _ref(quote: str) -> EvidenceRef:
    return EvidenceRef(
        source_id="source:tc01",
        source_sha256="a" * 64,
        page=1,
        exact_quote=quote,
    )


def _found(field: str, value: str | int, quote: str) -> FieldCandidate:
    return FieldCandidate(field=field, state="FOUND", value=value, refs=(_ref(quote),))


def _report(
    *,
    advance_reference: str | None = None,
    transaction_reference: str | None = None,
    purpose: str | None = None,
    amount: int | None = None,
) -> ReadResult:
    documents: list[DocumentAnalysis] = []
    settlement_fields = []
    if advance_reference is not None:
        settlement_fields.append(
            _found("advance_reference", advance_reference, advance_reference)
        )
    if purpose is not None:
        settlement_fields.append(_found("purpose", purpose, purpose))
    if amount is not None:
        settlement_fields.append(_found("declared_advance", amount, str(amount)))
    if settlement_fields:
        documents.append(
            DocumentAnalysis(
                source_id="source:tc01",
                document_id="source:tc01:1:SETTLEMENT_FORM",
                document_type="SETTLEMENT_FORM",
                fields=tuple(settlement_fields),
            )
        )
    if transaction_reference is not None:
        documents.append(
            DocumentAnalysis(
                source_id="source:receipt",
                document_id="source:receipt:1:PAYMENT_PROOF",
                document_type="PAYMENT_PROOF",
                fields=(
                    _found(
                        "transaction_reference",
                        transaction_reference,
                        transaction_reference,
                    ),
                ),
            )
        )
    return ReadResult(
        provider_mode="LIVE",
        data_origin="LIVE_READ",
        documents=tuple(documents),
    )


def _link(wf, report: ReadResult, *, tenant: str = TENANT, employee: str = EMPLOYEE):
    with wf.db.connect() as cx:
        return wf._settlement_link_for(
            cx,
            tenant=tenant,
            employee=employee,
            case_activity="activity:proposed:tc01-settlement",
            report=report,
        )


@pytest.mark.parametrize("kind", ["typed", "legacy"])
def test_references_reach_catalog_across_restart_and_same_payload_import(
    tmp_path: Path, kind: str
) -> None:
    context = _context_file(tmp_path, kind, ["TU-TC01"], suffix="v1")
    database = tmp_path / f"{kind}.sqlite"

    first = _compose(tmp_path, database, context)
    entry = first.catalog_entry(TENANT, _activity_id(kind))
    assert entry is not None
    assert entry.references == ("TU-TC01",)

    restarted = _compose(tmp_path, database, context)
    entry_after_restart = restarted.catalog_entry(TENANT, _activity_id(kind))
    assert entry_after_restart is not None
    assert entry_after_restart.references == ("TU-TC01",)
    with restarted.db.connect() as cx:
        assert cx.execute(
            "SELECT COUNT(*) FROM context_activities WHERE tenant = ? AND activity_id = ?",
            (TENANT, _activity_id(kind)),
        ).fetchone()[0] == 1
        snapshot = cx.execute(
            "SELECT payload_json FROM context_snapshots WHERE tenant = ?",
            (TENANT,),
        ).fetchone()
    snapshot_payload = json.loads(snapshot["payload_json"])
    snapshot_activities = (
        [snapshot_payload["activity"]]
        if kind == "typed"
        else snapshot_payload["activities"]
    )
    assert any("TU-TC01" in activity.get("references", []) for activity in snapshot_activities)


@pytest.mark.parametrize("kind", ["typed", "legacy"])
def test_new_context_version_replaces_removed_references(
    tmp_path: Path, kind: str
) -> None:
    database = tmp_path / f"{kind}.sqlite"
    first = _context_file(tmp_path, kind, ["TU-TC01"], suffix="v1")
    second = _context_file(tmp_path, kind, ["TU-TC01-NEW"], suffix="v2")
    _compose(tmp_path, database, first)

    updated = _compose(tmp_path, database, second)
    entry = updated.catalog_entry(TENANT, _activity_id(kind))
    assert entry is not None
    assert entry.references == ("TU-TC01-NEW",)
    assert "TU-TC01" not in entry.references
    assert _link(updated, _report(advance_reference="TU-TC01")).status == "NOT_FOUND"
    new_reference = _link(updated, _report(advance_reference="TU-TC01-NEW"))
    assert new_reference.status == "LINKED"
    assert new_reference.activity_id == _activity_id(kind)


@pytest.mark.parametrize("kind", ["typed", "legacy"])
def test_context_without_references_stays_unlinked_and_does_not_invent_one(
    tmp_path: Path, kind: str
) -> None:
    context = _context_file(tmp_path, kind, None, suffix="no-refs")
    wf = _compose(tmp_path, tmp_path / f"{kind}.sqlite", context)
    entry = wf.catalog_entry(TENANT, _activity_id(kind))
    assert entry is not None
    assert entry.references == ()


@pytest.mark.parametrize("kind", ["typed", "legacy"])
def test_malformed_reference_declaration_is_rejected_not_silently_dropped(
    tmp_path: Path, kind: str
) -> None:
    context = _context_file(tmp_path, kind, "TU-TC01", suffix="invalid")
    with pytest.raises((TypeError, ValueError)):
        _compose(tmp_path, tmp_path / f"{kind}.sqlite", context)


def test_imported_document_reference_links_without_transaction_code(tmp_path: Path) -> None:
    context = _context_file(tmp_path, "typed", ["TU-TC01"], suffix="link")
    wf = _compose(tmp_path, tmp_path / "link.sqlite", context)

    result = _link(wf, _report(advance_reference="TU-TC01"))

    assert result.status == "LINKED"
    assert result.activity_id == TC01
    assert result.basis == "DOCUMENT_REFERENCE"


def test_duplicate_imported_references_remain_ambiguous(tmp_path: Path) -> None:
    context = _context_file(tmp_path, "typed", ["TU-TC01"], suffix="duplicate")
    payload = json.loads(context.read_text(encoding="utf-8"))
    payload["activities"] = [
        {
            "activity_id": "activity:other",
            "name": "Hoạt động khác",
            "purpose": "Khác",
            "status": "AUTHORIZED",
            "references": ["TU-TC01"],
        }
    ]
    context.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    wf = _compose(tmp_path, tmp_path / "duplicate.sqlite", context)

    result = _link(wf, _report(advance_reference="TU-TC01"))

    assert result.status == "CONFLICT"
    assert result.activity_id is None
    assert len({candidate.activity_id for candidate in result.candidates}) == 2


def test_tenant_isolation_and_conflicting_basis_do_not_link_wrong_activity(
    tmp_path: Path,
) -> None:
    context = _context_file(tmp_path, "typed", ["TU-TC01"], suffix="tenant")
    payload = json.loads(context.read_text(encoding="utf-8"))
    payload["activities"] = [
        {
            "activity_id": "activity:other",
            "name": "Hoạt động khác",
            "purpose": "Khác",
            "status": "AUTHORIZED",
        }
    ]
    payload["ledger"].append(
        {
            "id": "other-advance",
            "external_key": "transfer:FT-OTHER-0001",
            "kind": "ADVANCE_RECEIVED",
            "scope": "activity:other",
            "payer": "company:bank-demo",
            "payee": EMPLOYEE,
            "amount": 4_000_000,
            "event_at": "2026-10-05T09:00:00+07:00",
            "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED",
            "allocation_state": "ALLOCATED",
        }
    )
    context.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    wf = _compose(tmp_path, tmp_path / "tenant.sqlite", context)

    other_tenant = _link(wf, _report(advance_reference="TU-TC01"), tenant="tenant:other")
    wrong_employee = _link(
        wf,
        _report(transaction_reference="FT-TC01-0001"),
        employee="employee:someone-else",
    )
    contradictory = _link(
        wf,
        _report(advance_reference="TU-TC01", transaction_reference="FT-OTHER-0001"),
    )

    assert other_tenant.status == "NOT_FOUND"
    assert wrong_employee.status == "CONFLICT"
    assert "employee" in wrong_employee.conflicting_fields
    assert contradictory.status == "CONFLICT"
    assert contradictory.activity_id is None


def test_weak_similarity_requires_confirmation_and_transaction_identity_still_links(
    tmp_path: Path,
) -> None:
    context = _context_file(tmp_path, "typed", None, suffix="weak")
    wf = _compose(tmp_path, tmp_path / "weak.sqlite", context)
    purpose = json.loads(context.read_text(encoding="utf-8"))["activity"]["purpose"]

    weak = _link(wf, _report(purpose=purpose, amount=4_000_000))
    transaction = _link(
        wf,
        _report(transaction_reference="FT-TC01-0001"),
    )

    assert weak.status == "NEEDS_CONFIRMATION"
    assert transaction.status == "LINKED"
    assert transaction.activity_id == TC01
    assert transaction.basis == "TRANSACTION_IDENTITY"
