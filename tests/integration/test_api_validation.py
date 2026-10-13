"""API boundary validation (contracts §1).

A timestamp without a timezone is invalid input and must be rejected at the
request boundary with 422 — never allowed to crash the handler as a 500.
"""

from __future__ import annotations


async def test_naive_occurred_at_is_a_422_not_a_500(app_fixture):
    response = await app_fixture.client.post(
        "/api/cases",
        json={
            "activity": {
                "mode": "new",
                "name": "Hoạt động thiếu timezone",
                "occurred_at": "2026-10-06T09:00:00",
                "declared_purpose": "p",
            }
        },
        headers={"X-Command-Id": "cmd-naive"},
    )
    assert response.status_code == 422, response.text
    assert app_fixture.case_count() == 0


async def test_proposed_activity_is_not_offered_as_existing_catalog(app_fixture):
    # A new-activity draft creates a PROPOSED context row, but the selectable
    # "existing" catalog must only offer AUTHORIZED activities — otherwise the
    # UI offers a choice the server then rejects.
    await app_fixture.client.post(
        "/api/cases",
        json={
            "activity": {
                "mode": "new",
                "name": "Hoạt động đề xuất",
                "occurred_at": "2026-10-06T09:00:00+07:00",
                "declared_purpose": "p",
            }
        },
        headers={"X-Command-Id": "cmd-proposed"},
    )
    catalog = (await app_fixture.client.get("/api/demo/session")).json()["activity_catalog"]
    statuses = {entry["status"] for entry in catalog}
    assert "PROPOSED" not in statuses
    assert all(entry["status"] == "AUTHORIZED" for entry in catalog)
