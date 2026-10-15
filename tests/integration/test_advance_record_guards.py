"""RecordActual advance guards via the real workflow (task 14/10/2026).

6.  Voucher payee != dossier employee -> advance stays OBSERVED, A not established.
8.  Reloading the same advance transaction -> idempotent, A counted once.
9.  Same external_key with different payer/payee/scope/amount -> conflict.
10. Same reference under another namespace -> a different transaction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    RecordActual,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import (
    CaseWorkflow,
    CommandConflictError,
    UnsupportedCommandError,
)

PILOT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "test-kit"
    / "uc03-pilot"
    / "f01-cong-tac-thu-lai-tien-thua"
)
TENANT = "tenant:uc03-pilot"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
ACTIVITY = "activity:uc03-f01"
PILOT_CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: PILOT_CLOCK)
    wf.enable_evidence_read(
        reader=object(), classifier=object(), artifacts_root=tmp_path / "a"
    )
    org = json.loads(
        (PILOT / "input" / "organization.json").read_text(encoding="utf-8")
    )
    org["ledger"] = []
    from invoice_referee.domain.organization import OrganizationContext

    wf.import_company_context(
        OrganizationContext.model_validate_json(json.dumps(org)), origin="SIMULATED"
    )
    return wf


async def _seed_draft(
    wf: CaseWorkflow,
    tag: str = "x",
    activity: str = ACTIVITY,
    employee: str = EMPLOYEE,
) -> str:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=employee)
    created = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=employee,
            command_id=f"cmd:1:{tag}",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=activity,
                name="a",
                occurred_at="2026-10-06T09:00:00+07:00",
                declared_purpose="p",
            )
        ),
    )
    root = created.case_view.id
    digest = hashlib.sha256(f"pdf:{tag}".encode()).hexdigest()
    await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id=f"cmd:2:{tag}",
            expected_case_version=created.case_view.version,
        ),
        AttachSources(
            root_id=root,
            uploads=(
                SourceUpload(
                    filename="hd.pdf",
                    media="PDF",
                    digest=digest,
                    storage_key=f"{TENANT}/{root}/hd.pdf",
                ),
            ),
        ),
    )
    return root


async def _record(
    wf: CaseWorkflow,
    root: str,
    *,
    key: str,
    payee: str = EMPLOYEE,
    payer: str = "company:demo",
    amount: int = 4_000_000,
    scope: str = ACTIVITY,
    command_id: str,
):
    version = int(
        wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    )
    session = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    return await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACCOUNTANT,
            command_id=command_id,
            expected_case_version=version,
        ),
        RecordActual(
            root_id=root,
            money=RecordMoneyInput(
                external_key=key,
                claimed_kind="ADVANCE_RECEIVED",
                claimed_scope=scope,
                payer=payer,
                payee=payee,
                amount=amount,
                event_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
                completion_claim="Kế toán đã kiểm tra chứng từ ứng và xác nhận đã giao.",
                reason="Ghi nhận tiền ứng thực nhận",
                instrument_method="TRANSFER",
                instrument_status="COMPLETED",
            ),
        ),
    )


def _advance_state(wf: CaseWorkflow, root: str):
    row = wf._query_one(
        "SELECT * FROM money_events WHERE tenant = ? AND root_id = ?", (TENANT, root)
    )
    with wf.db.transaction() as cx:
        case = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        view = wf._case_view(cx, case)
    return row, view


async def test_payee_mismatch_does_not_establish_a(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    await _record(
        wf,
        root,
        key="bank:ADV-WRONG-PAYEE",
        payee="employee:someone-else",
        command_id="cmd:r1",
    )
    row, view = _advance_state(wf, root)
    assert row["verification_state"] == "OBSERVED"
    assert (
        view.actual_money.A.state != "KNOWN"
        or getattr(view.actual_money.A, "value", None) != 4_000_000
    )


async def test_reload_same_advance_is_idempotent(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    await _record(wf, root, key="bank:ADV-SAME", command_id="cmd:r1")
    await _record(wf, root, key="bank:ADV-SAME", command_id="cmd:r2")
    rows = (
        wf.db.connect()
        .execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND external_key = ?",
            (TENANT, "bank:ADV-SAME"),
        )
        .fetchone()
    )
    assert int(rows["n"]) == 1


async def test_same_key_different_payee_conflicts(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    await _record(wf, root, key="bank:ADV-CONF", command_id="cmd:r1")
    with pytest.raises(CommandConflictError):
        await _record(
            wf,
            root,
            key="bank:ADV-CONF",
            payee="employee:someone-else",
            command_id="cmd:r2",
        )


async def test_event_identity_already_owned_by_another_case_conflicts(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    first_root = await _seed_draft(wf, tag="first", activity=ACTIVITY)
    second_root = await _seed_draft(
        wf, tag="second", activity=ACTIVITY, employee="employee:employee-b"
    )
    await _record(
        wf,
        first_root,
        key="bank:ADV-CROSS-ROOT",
        command_id="cmd:r1",
    )

    with pytest.raises(CommandConflictError, match="hồ sơ khác"):
        await _record(
            wf,
            second_root,
            key="bank:ADV-CROSS-ROOT",
            command_id="cmd:r2",
        )

    rows = wf.db.connect().execute(
        "SELECT root_id FROM money_events WHERE tenant = ? AND external_key = ?",
        (TENANT, "bank:ADV-CROSS-ROOT"),
    ).fetchall()
    assert [row["root_id"] for row in rows] == [first_root]


async def test_same_key_different_amount_conflicts(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    await _record(wf, root, key="bank:ADV-CONF2", command_id="cmd:r1")
    with pytest.raises(CommandConflictError):
        await _record(
            wf, root, key="bank:ADV-CONF2", amount=4_500_000, command_id="cmd:r2"
        )


async def test_same_reference_other_namespace_is_separate(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    await _record(wf, root, key="bank:PC-001", command_id="cmd:r1")
    await _record(wf, root, key="cash:PC-001", command_id="cmd:r2")
    rows = (
        wf.db.connect()
        .execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?",
            (TENANT, root),
        )
        .fetchone()
    )
    assert int(rows["n"]) == 2


async def test_rerecord_of_snapshot_history_does_not_double_a(tmp_path: Path) -> None:
    import json as _json

    from invoice_referee.domain.organization import OrganizationContext

    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    org = _json.loads(
        (PILOT / "input" / "organization.json").read_text(encoding="utf-8")
    )
    org["ledger"] = [
        {
            "id": "advance:UC03-F01",
            "external_key": "transfer:ADV-RE",
            "kind": "ADVANCE_RECEIVED",
            "scope": ACTIVITY,
            "payer": "company:demo",
            "payee": EMPLOYEE,
            "amount": 4_000_000,
            "event_at": "2026-10-05T09:00:00+07:00",
            "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED",
            "allocation_state": "ALLOCATED",
        }
    ]
    wf.import_company_context(
        OrganizationContext.model_validate_json(_json.dumps(org)), origin="SIMULATED"
    )
    await _record(wf, root, key="transfer:ADV-RE", command_id="cmd:r1")
    rows = (
        wf.db.connect()
        .execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND external_key = ?",
            (TENANT, "transfer:ADV-RE"),
        )
        .fetchone()
    )
    assert int(rows["n"]) == 0, "a witnessed history re-record must not insert again"


async def test_key_without_namespace_is_rejected_not_fabricated(
    tmp_path: Path,
) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    with pytest.raises(UnsupportedCommandError, match="namespace"):
        await _record(wf, root, key="ADV-NO-NAMESPACE", command_id="cmd:r1")
    rows = (
        wf.db.connect()
        .execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?",
            (TENANT, root),
        )
        .fetchone()
    )
    assert int(rows["n"]) == 0


async def test_foreign_source_ref_is_rejected(tmp_path: Path) -> None:
    from invoice_referee.domain.common import EvidenceRef

    wf = _workflow(tmp_path)
    root = await _seed_draft(wf)
    other = await _seed_draft(wf, tag="other", activity="activity:other")
    foreign = wf._query_one(
        "SELECT source_id, digest FROM case_sources WHERE root_id = ?", (other,)
    )
    session = wf.start_session(
        tenant=TENANT, persona="accountant", actor_id="employee:accountant-demo"
    )
    version = int(
        wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    )
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import RecordActual
    from invoice_referee.domain.finance import RecordMoneyInput

    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=session.session_id,
                actor_id="employee:accountant-demo",
                command_id="cmd:foreign-ref",
                expected_case_version=version,
            ),
            RecordActual(
                root_id=root,
                money=RecordMoneyInput(
                    external_key="bank:ADV-FOREIGN",
                    claimed_kind="ADVANCE_RECEIVED",
                    claimed_scope=ACTIVITY,
                    payer="company:demo",
                    payee=EMPLOYEE,
                    amount=4_000_000,
                    event_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
                    completion_claim="x",
                    refs=(
                        EvidenceRef(
                            source_id=str(foreign["source_id"]),
                            source_sha256=str(foreign["digest"]),
                            page=1,
                            exact_quote="4.000.000",
                        ),
                    ),
                    reason="r",
                    instrument_method="TRANSFER",
                    instrument_status="COMPLETED",
                ),
            ),
        )
