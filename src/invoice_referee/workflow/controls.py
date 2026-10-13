"""Control state: epochs, read-sets and the Stop/commit ordering (contracts §6, §10.3).

`control_epoch` increments on Stop/Resume. A commit that snapshotted an older
epoch is stale and must not create a new financial effect. Stop is atomic with
the commit: a worker that finishes after Stop writes no instruction.
"""

from __future__ import annotations

import sqlite3


class StaleControlError(RuntimeError):
    """A worker's snapshotted control epoch no longer matches the case."""


def current_epoch(cx: sqlite3.Connection, root_id: str) -> int:
    row = cx.execute("SELECT control_epoch FROM cases WHERE id = ?", (root_id,)).fetchone()
    return int(row["control_epoch"]) if row is not None else 0


def bump_epoch(cx: sqlite3.Connection, root_id: str, now: str) -> int:
    """Increment the control epoch (Stop/Resume). Returns the new epoch."""
    cx.execute(
        "UPDATE cases SET control_epoch = control_epoch + 1, updated_at = ? WHERE id = ?",
        (now, root_id),
    )
    return current_epoch(cx, root_id)


def assert_epoch_current(
    cx: sqlite3.Connection, root_id: str, snapshot_epoch: int
) -> None:
    """Raise if the case's control epoch moved since the snapshot (contracts §6)."""
    if current_epoch(cx, root_id) != snapshot_epoch:
        raise StaleControlError(
            "Hồ sơ đã Stop/Resume sau khi tác vụ bắt đầu; không commit kết quả cũ."
        )


def context_version(cx: sqlite3.Connection, tenant: str) -> int:
    """Aggregate version of authoritative context records (contracts §10.3).

    Any policy/grant/B/activity/exception change bumps this; a commit compares
    it against its snapshot so a stale authority can never commit.
    """
    grants = cx.execute(
        "SELECT COUNT(*) AS n, COALESCE(MAX(version), '') AS v FROM context_grants "
        "WHERE tenant = ?",
        (tenant,),
    ).fetchone()
    imports = cx.execute(
        "SELECT COUNT(*) AS n FROM context_imports WHERE tenant = ?", (tenant,)
    ).fetchone()
    return int(grants["n"]) + int(imports["n"])


def assert_context_current(
    cx: sqlite3.Connection, tenant: str, snapshot_version: int
) -> None:
    """Raise if the authoritative context moved since the snapshot (contracts §10.3)."""
    if context_version(cx, tenant) != snapshot_version:
        raise StaleControlError(
            "Quyền/ngân sách/context đã thay đổi sau khi tác vụ bắt đầu; không commit."
        )
