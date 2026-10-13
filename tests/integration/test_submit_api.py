"""Submit/Answer/Decide over HTTP (plan T6; contracts §9).

The API delegates to the same CaseWorkflow; a submit returns a CaseView whose
state and instructions come from persisted state, not from the request body.
"""

from __future__ import annotations

import json

GOOD_PDF = b"%PDF-1.4\nchung tu demo\n%%EOF\n"
EMPLOYEE = "employee:employee-a"


async def test_submit_over_http_returns_persisted_view(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id
    # Seed a STUB transcription for the root (the app reads it on submit).
    from invoice_referee.evaluation.models import Transcription, TranscriptionFact

    transcription = Transcription(
        facts=(
            TranscriptionFact(field="incurred", value=8_000_000, role="INVOICE"),
            TranscriptionFact(field="paid_employee", value=5_000_000, role="PAYMENT"),
            TranscriptionFact(field="paid_company", value=3_000_000, role="PAYMENT"),
            TranscriptionFact(field="advance", value=2_000_000, role="ADVANCE"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER"),
        )
    )
    conn = app_fixture.db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_transcriptions (root_id, transcription_json, "
            "created_at) VALUES (?, ?, ?)",
            (root, transcription.model_dump_json(), "2026-10-13T00:00:00+00:00"),
        )
    finally:
        conn.close()

    attached = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd-att", "X-Expected-Version": str(created.case_view.version)},
    )
    assert attached.status_code == 200
    version = attached.json()["case_view"]["version"]

    submitted = await app_fixture.client.post(
        f"/api/cases/{root}/submit",
        json={"activity_id": "activity:travel-a", "declared_purpose": "Công tác"},
        headers={"X-Command-Id": "cmd-submit", "X-Expected-Version": str(version)},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()["case_view"]
    assert body["state"] == "READY_TO_EXECUTE"
    assert len(body["instructions"]) == 1
    assert body["instructions"][0]["amount"] == 3_000_000


async def test_answer_over_http_wrong_owner_conflicts(app_fixture):
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    issue = next(i for i in v.issues if i.kind == "FACT")
    response = await app_fixture.client.post(
        f"/api/cases/{v.id}/answers",
        json={
            "issue_id": issue.id,
            "basis_id": "basis:x",
            "answer_kind": "FACT",
            "value": "employee:employee-a",
            "reason": "tôi trả",
        },
        headers={"X-Command-Id": "cmd-ans"},
    )
    # Employee is not the accountant owner -> the answer is not applied.
    assert response.status_code == 400
