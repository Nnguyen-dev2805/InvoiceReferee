"""B9 post-closure adjustment: a new linked child preserving the old closure.

Integration over the REAL pipeline (fake reader). No LIVE, no .env, no mocked
COMPLETE report. The closed case is byte-identical; a new child carries the same
employee/work/B3 with an adjustment origin link.
"""
from __future__ import annotations

import pytest

from invoice_referee.shared.errors import DomainError
from tests.settlement.test_b3_workflow import (  # noqa: F401 — fixture chain
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_workflow import ready_linked_b7  # noqa: F401
from tests.settlement.test_b7_fulfillment import (  # noqa: F401
    approved_linked_b7, _money_text, money_payload, upload_money_proof, _record,
)
from tests.settlement.test_b7_closure import (  # noqa: F401
    _receipt, _refresh_rerun_revalidate, _close,
)


def _closed_child(svc, child, decision):
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    _close(svc, child.id, final.run_id, "1", decision.id)
    return svc.get_case(child.id)


def test_adjustment_keeps_old_closure_and_links(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    closed_version = closed.case_version
    closed_stage = closed.stage
    adj = svc.prepare_b7_adjustment(closed.id, {"reason": "Có khoản chi mới"},
        command("adj", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    assert adj.id != closed.id
    assert adj.linked_b7.origin.adjustment_of_case_id == closed.id
    assert adj.linked_b7.origin.origin_case_id == child.linked_b7.origin.origin_case_id
    assert adj.submission.work_ref == closed.submission.work_ref
    assert adj.submission.employee_ref == closed.submission.employee_ref
    # The closed case is unchanged (still closed at the same version).
    old = svc.get_case(closed.id)
    assert old.stage == closed_stage
    assert old.case_version == closed_version
    assert svc.closed(closed.id) is True


def test_adjustment_requires_closed_case(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.prepare_b7_adjustment(child.id, {"reason": "x"},
            command("adj", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "B7_WORKFLOW_BLOCKED"


def test_adjustment_wrong_role_rejected(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    with pytest.raises(DomainError) as exc:
        svc.prepare_b7_adjustment(closed.id, {"reason": "x"},
            command("adj", "NV-DEMO-01", "ACCOUNTANT", closed.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_adjustment_same_key_reuses_child(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    body = {"reason": "Có khoản chi mới"}
    first = svc.prepare_b7_adjustment(closed.id, body,
        command("same", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    replay = svc.prepare_b7_adjustment(closed.id, body,
        command("same", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    assert replay.id == first.id


def test_active_adjustment_reused_not_duplicated(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    first = svc.prepare_b7_adjustment(closed.id, {"reason": "A"},
        command("adj-1", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    # A second, different command must not create a second active settlement.
    second = svc.prepare_b7_adjustment(closed.id, {"reason": "B"},
        command("adj-2", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    assert second.id == first.id


def test_adjustment_new_expense_reaches_policy_unresolved(approved_linked_b7):
    """A new 0.5M expense raises T beyond B → POLICY unresolved, not approved0.5."""
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    adj = svc.prepare_b7_adjustment(closed.id, {"reason": "Thêm chi phí"},
        command("adj", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    # The new child starts fresh (report-only); no carried approval/receipt.
    view = svc.get_case(adj.id)
    assert view.stage == "CHECKING"
    assert view.b7_workflow.status == "NOT_PRESENTED"
    assert view.b7_workflow.decision is None
    assert not svc.closed(adj.id)


def test_adjustment_upload_allowed_on_open_child(approved_linked_b7):
    """A draft adjustment child accepts new sources; the old closure is intact."""
    from invoice_referee.settlement.models import Upload
    svc, child, report, decision = approved_linked_b7
    closed = _closed_child(svc, child, decision)
    adj = svc.prepare_b7_adjustment(closed.id, {"reason": "Thêm chi phí"},
        command("adj", "ACC-DEMO-01", "ACCOUNTANT", closed.case_version))
    record = svc.add_source(adj.id, Upload(filename="new.txt", content=b"chi phi"),
        command("src", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(adj.id).case_version))
    assert record.id.startswith("S-")
    assert svc.get_case(closed.id).stage == "SETTLEMENT_CLOSED"
