"""SQLite plumbing for the workflow (contracts §6).

WAL, busy timeout and short BEGIN IMMEDIATE write transactions; one process
owns the file. No business logic lives here.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# The schema version this code expects. Bump when schema.sql gains a change that
# must be applied to an existing DB (contracts §6: versioned migration, no
# Alembic; a failed migration rolls back and keeps the old version).
SCHEMA_VERSION = 2

# Additive column migrations applied to an existing DB, keyed by version. Each
# entry is (table, column, ddl) applied only when the column is missing; the
# CREATE TABLE IF NOT EXISTS script already creates them for a fresh DB.
_COLUMN_MIGRATIONS: dict[int, tuple[tuple[str, str, str], ...]] = {
    1: (
        (
            "context_grants",
            "allowed_profiles_json",
            "ALTER TABLE context_grants ADD COLUMN allowed_profiles_json TEXT NOT NULL DEFAULT '[]'",
        ),
    ),
    2: (
        (
            "jobs",
            "input_basis_json",
            "ALTER TABLE jobs ADD COLUMN input_basis_json TEXT NOT NULL DEFAULT '{}'",
        ),
    ),
}


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


class Database:
    """Thin connection factory + migration runner for one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def migrate(self) -> None:
        """Create the schema and apply versioned, additive column migrations.

        Runs inside one transaction per version so a failure rolls back and the
        previous data (actual money, instructions, audit) is preserved.
        """
        connection = self.connect()
        try:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            for version in range(current + 1, SCHEMA_VERSION + 1):
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for table, column, ddl in _COLUMN_MIGRATIONS.get(version, ()):
                        if not _column_exists(connection, table, column):
                            connection.execute(ddl)
                    connection.execute(f"PRAGMA user_version = {version}")
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One short write transaction; the caller does all its work inside."""
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
