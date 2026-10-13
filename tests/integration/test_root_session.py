"""T2 integration checks: canonical root, tenant/session scope and sources.

Plan T2 RED list: root unique, concurrent create, client role cannot grant,
tenantB no view/reset tenantA, source bad media/size clear error with no
financial mutation — plus the produced command surface (attach/revise) and
the session cookie/persona audit the task implements.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from invoice_referee.domain.commands import Declaration, SourceUpload
from invoice_referee.workflow.service import (
    DEFAULT_MAX_SOURCE_BYTES,
    StaleCommandError,
)

TENANT_A = "tenant:demo"
TENANT_B = "tenant:b"
EMPLOYEE = "employee:employee-a"
GOOD_PDF = b"%PDF-1.4\nchung tu demo\n%%EOF\n"


def upload(name: str = "hoadon.pdf") -> SourceUpload:
    return SourceUpload(
        filename=name,
        media="PDF",
        digest="0" * 64,
        storage_key=f"{TENANT_A}/root/{name}",
    )


async def test_same_activity_has_one_root(app_fixture):
    a = await app_fixture.create(employee="employee:a", activity="activity:travel-a")
    b = await app_fixture.create(employee="employee:a", activity="activity:travel-a")
    assert a.case_view.id == b.case_view.id
    assert app_fixture.case_count(TENANT_A) == 1


async def test_concurrent_create_single_root(app_fixture):
    a, b = await asyncio.gather(
        app_fixture.create(employee="employee:a", activity="activity:travel-a"),
        app_fixture.create(employee="employee:a", activity="activity:travel-a"),
    )
    assert a.case_view.id == b.case_view.id
    assert app_fixture.case_count(TENANT_A) == 1


async def test_two_activities_two_roots(app_fixture):
    a = await app_fixture.create(employee="employee:a", activity="activity:travel-a")
    b = await app_fixture.create(employee="employee:a", activity="activity:travel-b")
    assert a.case_view.id != b.case_view.id
    assert app_fixture.case_count(TENANT_A) == 2


async def test_client_role_or_budget_cannot_become_authority(app_fixture):
    rejected = await app_fixture.client.post(
        "/api/cases",
        json={
            "activity": {
                "mode": "new",
                "name": "Tiếp khách địa phương",
                "occurred_at": "2026-10-06T09:00:00+07:00",
                "declared_purpose": "Làm việc với đối tác",
            },
            "role": "approver",
            "budget": 8_000_000,
        },
    )
    assert rejected.status_code == 422

    created = await app_fixture.create(
        employee="employee:a",
        activity="activity:unknown-z",
        activity_name="Hoạt động chưa có context",
    )
    view = created.case_view
    assert view.state == "DRAFT"
    assert any(issue.kind == "FACT" for issue in view.issues)
    # Missing context is not a fabricated zero: no B row at all.
    assert app_fixture.budget_amount("activity:unknown-z") is None
    assert app_fixture.budget_amount("activity:travel-b") is None


async def test_tenant_b_cannot_view_or_reset_tenant_a(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id
    owner_ctx = app_fixture.ctx(actor=EMPLOYEE)
    before = app_fixture.view(owner_ctx, root)

    tenant_b = app_fixture.client_for(tenant=TENANT_B)
    assert (await tenant_b.get(f"/api/cases/{root}")).status_code == 404

    listed = await tenant_b.get("/api/cases")
    assert listed.status_code == 200
    assert root not in {case["id"] for case in listed.json()["cases"]}

    blocked = await tenant_b.post(
        f"/api/cases/{root}/sources",
        files={"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd-b-1", "X-Expected-Version": "1"},
    )
    assert blocked.status_code == 404

    after = app_fixture.view(owner_ctx, root)
    assert after.version == before.version
    assert after.sources == before.sources


async def test_bad_source_media_and_size_rejected_without_financial_mutation(app_fixture):
    # Contracts §6 pilot ceiling: 20MiB/file. The fixture injects a smaller
    # cap for the oversize case; the shipped default must stay 20 MiB.
    assert DEFAULT_MAX_SOURCE_BYTES == 20 * 1024 * 1024

    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id
    owner_ctx = app_fixture.ctx(actor=EMPLOYEE)
    before = app_fixture.view(owner_ctx, root)

    bad_media = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("ghichu.txt", b"khong phai chung tu", "text/plain")},
        headers={"X-Command-Id": "cmd-media-1", "X-Expected-Version": str(before.version)},
    )
    assert bad_media.status_code == 415
    assert "không hỗ trợ" in bad_media.json()["detail"]

    oversize = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={
            "files": (
                "scan.pdf",
                b"%PDF-1.4" + b"0" * app_fixture.workflow.max_source_bytes,
                "application/pdf",
            )
        },
        headers={"X-Command-Id": "cmd-size-1", "X-Expected-Version": str(before.version)},
    )
    assert oversize.status_code == 413
    assert "quá lớn" in oversize.json()["detail"]

    rejected_state = app_fixture.view(owner_ctx, root)
    assert rejected_state.version == before.version
    assert rejected_state.sources == ()
    assert app_fixture.financial_row_count() == 0

    accepted = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd-good-1", "X-Expected-Version": str(before.version)},
    )
    assert accepted.status_code == 200
    after = app_fixture.view(owner_ctx, root)
    assert [source.media for source in after.sources] == ["PDF"]
    assert after.version == before.version + 1


async def test_stale_expected_version_is_rejected(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id

    stale_ctx = app_fixture.ctx(actor=EMPLOYEE, expected_case_version=0)
    with pytest.raises(StaleCommandError):
        await app_fixture.attach(stale_ctx, root, (upload(),))

    stale_http = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd-stale-1", "X-Expected-Version": "0"},
    )
    assert stale_http.status_code == 409


async def test_attach_and_revise_flow(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id

    attached = await app_fixture.attach(
        app_fixture.ctx(actor=EMPLOYEE, expected_case_version=1), root, (upload(),)
    )
    assert len(attached.case_view.sources) == 1
    assert attached.case_view.sources[0].digest == "0" * 64

    revised = await app_fixture.revise(
        app_fixture.ctx(actor=EMPLOYEE, expected_case_version=2),
        root,
        Declaration(
            activity_id="activity:travel-a",
            declared_purpose="Công tác Hà Nội",
            notes="Bổ sung mục đích sau khi đối chiếu",
        ),
    )
    assert revised.case_view.version == 3
    assert app_fixture.input_revision(root) == 3


async def test_tenant_b_activity_context_is_not_shared(app_fixture):
    created = await app_fixture.create(
        employee="employee:b",
        tenant=TENANT_B,
        activity="activity:travel-a",
        activity_name="Công tác của tenant B",
    )
    view = created.case_view
    assert view.state == "DRAFT"
    assert "Công tác Hà Nội" not in view.summary
    assert any(issue.kind == "FACT" for issue in view.issues)
    # Tenant demo's committed seed is untouched, and no cross-tenant row exists.
    assert app_fixture.budget_amount("activity:travel-a") == 8_000_000
    row = app_fixture.query_one(
        "SELECT budget_amount FROM context_activities WHERE tenant = ? "
        "AND activity_id = ?",
        (TENANT_B, "activity:travel-a"),
    )
    assert row is None or row["budget_amount"] is None


async def test_session_cookie_is_httponly_and_persona_switch_is_audited(app_fixture):
    fresh = app_fixture.fresh_client()
    session_response = await fresh.get("/api/demo/session")
    assert session_response.status_code == 200
    assert "httponly" in session_response.headers["set-cookie"].lower()

    body = session_response.json()
    assert body["session"]["tenant"] == TENANT_A
    assert body["session"]["persona"] == "employee"
    assert body["activity_catalog"]

    switched = await fresh.post("/api/demo/persona", json={"persona": "accountant"})
    assert switched.status_code == 200
    assert switched.json()["session"]["persona"] == "accountant"
    assert "PERSONA_SWITCH" in app_fixture.audit_actions()


async def test_catalog_activity_reports_seeded_budget(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    assert app_fixture.budget_amount("activity:travel-a") == 8_000_000
    assert not any(issue.kind == "FACT" for issue in created.case_view.issues)


async def test_activity_proposed_through_api_gets_server_generated_id(app_fixture):
    response = await app_fixture.client.post(
        "/api/cases",
        json={
            "activity": {
                "mode": "new",
                "name": "Tiếp khách địa phương",
                "occurred_at": "2026-10-06T09:00:00+07:00",
                "declared_purpose": "Làm việc với đối tác",
            }
        },
        headers={"X-Command-Id": "cmd-new-1"},
    )
    assert response.status_code == 200
    case = response.json()["case_view"]
    assert case["state"] == "DRAFT"
    assert any(issue["kind"] == "FACT" for issue in case["issues"])
    assert app_fixture.case_count(TENANT_A) == 1
