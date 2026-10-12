"""Tests for business-meaningful case ID formats (TU-YYMM-XXX, QT-YYMM-XXX, TC-YYMM-XXX)."""
from __future__ import annotations

from datetime import datetime, timezone
import pytest

from invoice_referee.settlement.b3_intake import B3CompanyContext
from invoice_referee.settlement.models import Command, Submission
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")


@pytest.fixture
def service(store):
    return Service(
        store,
        StructuredLedgerReader(store.artifact_root),
        config=ServiceConfig(
            authority=[],
            b3_context=B3CompanyContext.model_validate(CONTEXT),
        ),
    )


def test_b3_case_id_format_and_sequence(service, store):
    """B3 advance cases must have ID prefix TU-YYMM- and be sequential."""
    yymm = datetime.now(timezone.utc).strftime("%y%m")
    expected_prefix = f"TU-{yymm}-"

    cmd1 = Command(key="cmd-1", actor_id="NV-DEMO-01", demo_role="EMPLOYEE",
                   expected_case_version=None, body={})
    from invoice_referee.settlement.b3_intake import B3Intake

    intake = B3Intake.model_validate(NATIVE_FORM)
    case1 = service.submit_b3("NV-DEMO-01", intake, cmd1)
    assert case1.id == f"{expected_prefix}001"

    cmd2 = Command(key="cmd-2", actor_id="NV-DEMO-01", demo_role="EMPLOYEE",
                   expected_case_version=None, body={})
    case2 = service.submit_b3("NV-DEMO-01", intake, cmd2)
    assert case2.id == f"{expected_prefix}002"


def test_standalone_b7_case_id_format(service, store):
    """Standalone self-paid B7 cases must have ID prefix TC-YYMM-."""
    from invoice_referee.settlement.models import B7StandaloneIntake

    yymm = datetime.now(timezone.utc).strftime("%y%m")
    expected_prefix = f"TC-{yymm}-"

    intake = B7StandaloneIntake(purpose="Công tác", scope="Tự chi")
    cmd = Command(key="cmd-tc-1", actor_id="NV-DEMO-01", demo_role="EMPLOYEE",
                  expected_case_version=None, body={})
    case = service.submit_standalone_b7("NV-DEMO-01", intake, cmd)
    assert case.id == f"{expected_prefix}001"


def test_linked_b7_case_id_format(service, store):
    """Linked B7 cases must have ID prefix QT-YYMM-."""
    from invoice_referee.settlement.b3_intake import B3Intake

    yymm = datetime.now(timezone.utc).strftime("%y%m")
    expected_prefix = f"QT-{yymm}-"

    # Create parent B3 case
    intake = B3Intake.model_validate(NATIVE_FORM)
    cmd_b3 = Command(key="cmd-b3", actor_id="NV-DEMO-01", demo_role="EMPLOYEE",
                     expected_case_version=None, body={})
    parent = service.submit_b3("NV-DEMO-01", intake, cmd_b3)

    # Prepare linked B7 child
    cmd_linked = Command(key="cmd-link", actor_id="NV-DEMO-01", demo_role="EMPLOYEE",
                         expected_case_version=parent.case_version, body={})
    child = store.prepare_linked_b7(parent.id, cmd_linked)
    assert child.id == f"{expected_prefix}001"
