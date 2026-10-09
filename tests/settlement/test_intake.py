"""W01 intake slice: case creation, sources, revisions and command guards.

RED per plan W01: create → upload original → reload → stale edit must not
overwrite; command retry with the same key and a different payload must be
rejected. Fixtures below are the ones frozen in the plan.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Command, Submission, Upload
from invoice_referee.settlement.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cases.sqlite", tmp_path / "sources")


@pytest.fixture
def submission():
    cutoff = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)
    return Submission(employee_ref="NV-01", work_ref="CT-01", job="B7",
                      money_as_of=cutoff, knowledge_cutoff=cutoff,
                      form={"purpose": "Công tác A"})


@pytest.fixture
def command():
    return Command(key="create-1", actor_id="NV-01", demo_role="EMPLOYEE",
                   expected_case_version=None, body={})


def revision_command(case, key, actor="NV-01"):
    return Command(key=key, actor_id=actor, demo_role="EMPLOYEE",
                   expected_case_version=case.case_version,
                   body={"reason": "Bổ sung mục đích"})


def upload_command(case, key, actor="NV-01"):
    return Command(key=key, actor_id=actor, demo_role="EMPLOYEE",
                   expected_case_version=case.case_version, body={})


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n" + b"0" * 64
)
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\nendobj\ntrailer\n%%EOF"
CSV_BYTES = (
    "source_record_ref,event_kind,payer_ref,payee_ref,gross_amount_vnd,"
    "currency,event_at,reported_status\n"
    "TX-01,DISBURSEMENT,ORG-01,NV-01,2000000,VND,2026-10-06T09:00:00+07:00,"
    "completed\n"
).encode("utf-8")


def test_stale_revision_preserves_the_new_submission(store, submission, command):
    created = store.create_case(submission, command)
    current = store.revise(created.id, submission.model_copy(update={"form": {"purpose": "Công tác A"}}),
                           command.model_copy(update={"key": "edit-1", "expected_case_version": created.case_version}))
    with pytest.raises(DomainError) as error:
        store.revise(created.id, submission, command.model_copy(update={"key": "edit-2", "expected_case_version": created.case_version}))
    assert error.value.code == "STALE_VERSION"
    assert store.get_case(created.id).case_version == current.case_version


def test_retry_same_key_same_payload_returns_current_state(store, submission, command):
    created = store.create_case(submission, command)
    store.revise(created.id, submission.model_copy(update={"form": {"purpose": "Công tác B"}}),
                 revision_command(created, "edit-1"))
    replayed = store.create_case(submission, command)
    assert replayed.id == created.id
    assert replayed.case_version == 2
    assert store.get_case(created.id).submission.form["purpose"] == "Công tác B"


def test_retry_same_key_different_payload_conflicts(store, submission, command):
    store.create_case(submission, command)
    with pytest.raises(DomainError) as error:
        store.create_case(submission.model_copy(update={"work_ref": "CT-02"}), command)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_add_source_keeps_original_bytes_and_both_same_byte_uploads(store, submission, command):
    created = store.create_case(submission, command)
    first = store.add_source(created.id, Upload(filename="hoa-don.png", content=PNG_BYTES),
                             upload_command(created, "src-1"))
    current = store.get_case(created.id)
    second = store.add_source(created.id, Upload(filename="hoa-don.png", content=PNG_BYTES),
                              upload_command(current, "src-2"))
    assert first.id != second.id
    view = store.get_case(created.id)
    assert len(view.sources) == 2
    assert {s.filename for s in view.sources} == {"hoa-don.png"}
    assert first.sha256 == second.sha256
    for record in (first, second):
        assert (store.artifact_root / record.original_path).read_bytes() == PNG_BYTES


def test_add_source_rejects_oversize_file_without_side_effects(store, submission, command):
    created = store.create_case(submission, command)
    oversize = b"a" * (20 * 1024 * 1024 + 1)
    with pytest.raises(DomainError) as error:
        store.add_source(created.id, Upload(filename="bang-ke.csv", content=oversize),
                         upload_command(created, "src-1"))
    assert error.value.code == "FILE_TOO_LARGE"
    view = store.get_case(created.id)
    assert view.sources == []
    assert view.case_version == created.case_version


def test_add_source_rejects_unsupported_format_as_technical_error(store, submission, command):
    created = store.create_case(submission, command)
    docx_like = b"PK\x03\x04" + b"0" * 32
    with pytest.raises(DomainError) as error:
        store.add_source(created.id, Upload(filename="hop-dong.docx", content=docx_like),
                         upload_command(created, "src-1"))
    assert error.value.code == "UNSUPPORTED_FORMAT"
    view = store.get_case(created.id)
    assert view.sources == []
    assert view.case_version == created.case_version


def test_history_links_create_revise_and_source(store, submission, command):
    created = store.create_case(submission, command)
    store.revise(created.id, submission.model_copy(update={"form": {"purpose": "Công tác B"}}),
                 revision_command(created, "edit-1"))
    current = store.get_case(created.id)
    store.add_source(current.id, Upload(filename="sao-ke.csv", content=CSV_BYTES),
                     upload_command(current, "src-1"))
    history = store.history(created.id)
    kinds = [entry.kind for entry in history]
    assert kinds == ["CASE_CREATED", "SUBMISSION_REVISED", "SOURCE_ADDED"]
    assert all(entry.actor_id == "NV-01" for entry in history)


def test_get_unknown_case_raises_domain_error(store):
    with pytest.raises(DomainError) as error:
        store.get_case("C-404")
    assert error.value.code == "CASE_NOT_FOUND"


# --- API slice: create → upload → reload → open original → stale 409 ----------


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from invoice_referee.api.settlement import create_runtime_app

    app = create_runtime_app(db_path=tmp_path / "cases.sqlite",
                             artifact_root=tmp_path / "sources")
    return TestClient(app)


SUBMISSION_PAYLOAD = {
    "employee_ref": "NV-01",
    "work_ref": "CT-01",
    "job": "B7",
    "money_as_of": "2026-10-08T11:00:00Z",
    "knowledge_cutoff": "2026-10-08T11:00:00Z",
    "form": {"purpose": "Công tác A"},
}


def test_api_create_upload_reload_open_original_and_stale_edit_blocked(client):
    create = client.post("/api/cases", json={
        "submission": SUBMISSION_PAYLOAD,
        "actor_id": "NV-01",
        "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "api-create-1"})
    assert create.status_code == 201, create.text
    case = create.json()
    assert case["stage"] == "CHECKING"
    assert case["case_version"] == 1
    assert case["sources"] == []
    actions = {a["action"] for a in case["allowed_actions"]}
    assert "ADD_SOURCE" in actions

    upload = client.post(f"/api/cases/{case['id']}/sources",
                         files={"file": ("hoa-don.png", PNG_BYTES, "application/octet-stream")},
                         data={"actor_id": "NV-01", "demo_role": "EMPLOYEE", "expected_case_version": "1"},
                         headers={"Idempotency-Key": "src-1"})
    assert upload.status_code == 201, upload.text
    source = upload.json()

    reloaded = client.get(f"/api/cases/{case['id']}").json()
    assert len(reloaded["sources"]) == 1
    assert reloaded["case_version"] == 2

    content = client.get(f"/api/sources/{source['id']}/content")
    assert content.status_code == 200
    assert content.content == PNG_BYTES
    assert content.headers["content-type"].startswith("image/png")

    stale = client.patch(f"/api/cases/{case['id']}/submission", json={
        "submission": dict(SUBMISSION_PAYLOAD, form={"purpose": "Công tác B"}),
        "actor_id": "NV-01",
        "demo_role": "EMPLOYEE",
        "expected_case_version": 1,
    }, headers={"Idempotency-Key": "edit-1"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "STALE_VERSION"

    after = client.get(f"/api/cases/{case['id']}").json()
    assert after["case_version"] == 2
    assert after["submission"]["form"]["purpose"] == "Công tác A"

    history = client.get(f"/api/cases/{case['id']}/history").json()
    assert [e["kind"] for e in history] == ["CASE_CREATED", "SOURCE_ADDED"]


def test_api_command_retry_same_key_different_payload_is_409(client):
    payload = {"submission": SUBMISSION_PAYLOAD, "actor_id": "NV-01", "demo_role": "EMPLOYEE"}
    first = client.post("/api/cases", json=payload, headers={"Idempotency-Key": "api-create-1"})
    assert first.status_code == 201
    replay = client.post("/api/cases", json=payload, headers={"Idempotency-Key": "api-create-1"})
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    conflict = client.post("/api/cases",
                           json={"submission": dict(SUBMISSION_PAYLOAD, work_ref="CT-02"),
                                 "actor_id": "NV-01", "demo_role": "EMPLOYEE"},
                           headers={"Idempotency-Key": "api-create-1"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_api_unsupported_and_oversize_uploads_are_technical_not_business(client):
    create = client.post("/api/cases", json={
        "submission": SUBMISSION_PAYLOAD, "actor_id": "NV-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "api-create-1"})
    case_id = create.json()["id"]

    unsupported = client.post(f"/api/cases/{case_id}/sources",
                              files={"file": ("hop-dong.docx", b"PK\x03\x04" + b"0" * 32,
                                              "application/octet-stream")},
                              data={"actor_id": "NV-01", "demo_role": "EMPLOYEE", "expected_case_version": "1"},
                              headers={"Idempotency-Key": "src-1"})
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "UNSUPPORTED_FORMAT"

    oversize = client.post(f"/api/cases/{case_id}/sources",
                           files={"file": ("bang-ke.csv", b"a" * (20 * 1024 * 1024 + 1),
                                           "text/csv")},
                           data={"actor_id": "NV-01", "demo_role": "EMPLOYEE", "expected_case_version": "1"},
                           headers={"Idempotency-Key": "src-2"})
    assert oversize.status_code == 413
    assert oversize.json()["code"] == "FILE_TOO_LARGE"

    view = client.get(f"/api/cases/{case_id}").json()
    assert view["sources"] == []
    assert view["stage"] == "CHECKING"


def test_api_lists_created_cases(client):
    client.post("/api/cases", json={
        "submission": SUBMISSION_PAYLOAD, "actor_id": "NV-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "api-create-1"})
    listing = client.get("/api/cases").json()
    assert len(listing) == 1
    assert listing[0]["job"] == "B7"
