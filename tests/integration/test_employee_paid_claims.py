"""A2 employee paid-claim command-boundary tests (plan A2; ADR0007/Q32).

The responsible employee states a paid claim at submit. The server — never the
client — derives the actor, scope and time, and resolves the claim's file refs
to the uploaded source bytes. A stale digest or a ref that is not in this root is
rejected. A repeated command id is idempotent, and a stale case version conflicts
without a partial write.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import Declaration, EmployeePaidClaim, Submit
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.workflow.service import StaleCommandError, UnsupportedCommandError
from tests.conftest import AppFixture, TENANT_DEMO, DEFAULT_ACTOR, upload

ACTIVITY = "activity:travel-a"
SHA = "a" * 64


async def _draft_with_source(fx: AppFixture, *, digest: str = SHA) -> str:
    created = await fx.create(employee=DEFAULT_ACTOR, activity=ACTIVITY)
    root = created.case_view.id
    await fx.attach(
        fx.ctx(expected_case_version=created.case_view.version),
        root,
        (upload("hd.pdf"),),
    )
    return root


def _claim(*, digest: str = SHA, amount: int = 3_240_000) -> EmployeePaidClaim:
    return EmployeePaidClaim(
        invoice_reference="IR26101001",
        amount=amount,
        refs=(EvidenceRef(source_id="file:hd.pdf", source_sha256=digest, page=1, exact_quote="3.240.000 đ"),),
        reason="đã trực tiếp thanh toán",
    )


async def _real_source_id(app_fixture: AppFixture, root: str) -> tuple[str, str]:
    cx = app_fixture.db.connect()
    try:
        row = cx.execute(
            "SELECT source_id, digest FROM case_sources WHERE root_id = ? LIMIT 1", (root,)
        ).fetchone()
    finally:
        cx.close()
    return str(row["source_id"]), str(row["digest"])


async def _submit(fx: AppFixture, root: str, *, version: int, claims: tuple[EmployeePaidClaim, ...]):
    return await fx.workflow.execute(
        fx.ctx(expected_case_version=version),
        Submit(
            root_id=root,
            declaration=Declaration(activity_id=ACTIVITY, declared_purpose="Công tác"),
            employee_paid_claims=claims,
        ),
    )


async def test_own_scope_claim_is_accepted(app_fixture: AppFixture) -> None:
    root = await _draft_with_source(app_fixture)
    result = await _submit(app_fixture, root, version=2, claims=(_claim(),))
    cx = app_fixture.db.connect()
    try:
        rows = cx.execute(
            "SELECT fact_key, actor, scope FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchall()
    finally:
        cx.close()
    assert rows, "the claim must be persisted as a scoped confirmation"
    assert rows[0]["actor"] == DEFAULT_ACTOR  # server-derived, never the client's
    assert rows[0]["scope"] == ACTIVITY
    assert result.case_view.id == root


async def test_claim_with_foreign_digest_is_rejected(app_fixture: AppFixture) -> None:
    root = await _draft_with_source(app_fixture, digest=SHA)
    with pytest.raises(UnsupportedCommandError):
        await _submit(app_fixture, root, version=2, claims=(_claim(digest="b" * 64),))


async def test_repeated_command_id_is_idempotent(app_fixture: AppFixture) -> None:
    root = await _draft_with_source(app_fixture)
    session = app_fixture.session_for(TENANT_DEMO)
    context = CommandContext(
        session_id=session, actor_id=DEFAULT_ACTOR,
        command_id="cmd:fixed-id", expected_case_version=2,
    )
    command = Submit(
        root_id=root,
        declaration=Declaration(activity_id=ACTIVITY, declared_purpose="Công tác"),
        employee_paid_claims=(_claim(amount=1_000),),
    )
    first = await app_fixture.workflow.execute(context, command)
    second = await app_fixture.workflow.execute(context, command)
    assert second.duplicate_command is True
    assert second.case_view.version == first.case_view.version


async def test_stale_version_conflicts_without_partial_write(app_fixture: AppFixture) -> None:
    root = await _draft_with_source(app_fixture)
    with pytest.raises(StaleCommandError):
        await _submit(app_fixture, root, version=0, claims=(_claim(),))
    cx = app_fixture.db.connect()
    try:
        n = cx.execute(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchone()["n"]
    finally:
        cx.close()
    assert int(n) == 0


async def test_claim_can_reference_a_server_source_id(app_fixture: AppFixture) -> None:
    # The UI must be able to reference the document by its server source_id (the
    # stable, server-checked id), not a reconstructed filename. The backend
    # accepts a ref whose source_id IS the case source id.
    root = await _draft_with_source(app_fixture)
    source_id, digest = await _real_source_id(app_fixture, root)
    claim = EmployeePaidClaim(
        invoice_reference="IR26101001", amount=3_240_000,
        refs=(EvidenceRef(source_id=source_id, source_sha256=digest, page=1, exact_quote="3.240.000 đ"),),
        reason="đã trực tiếp thanh toán",
    )
    result = await _submit(app_fixture, root, version=2, claims=(claim,))
    assert result.case_view.id == root
    cx = app_fixture.db.connect()
    try:
        rows = cx.execute(
            "SELECT refs_json FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchall()
    finally:
        cx.close()
    assert rows, "a server-source-id claim must be accepted and persisted"


async def test_submit_for_another_activity_is_rejected(app_fixture: AppFixture) -> None:
    # A submit that declares a different activity than the root must not be
    # folded into this dossier (the declaration is not free-floating).
    root = await _draft_with_source(app_fixture)
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(
            app_fixture.ctx(expected_case_version=2),
            Submit(
                root_id=root,
                declaration=Declaration(activity_id="activity:other", declared_purpose="Công tác"),
                employee_paid_claims=(_claim(),),
            ),
        )
