"""Reset one S6 fixture DB to context-only (no dossiers). Usage: reset_s6_db.py <db>."""

import sqlite3
import sys

db = sqlite3.connect(sys.argv[1])
tables = [
    r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
]
for table in tables:
    cols = [c[1] for c in db.execute(f"PRAGMA table_info({table})")]
    if "root_id" in cols and table != "cases":
        db.execute(f"DELETE FROM {table}")
db.execute("DELETE FROM cases")
db.execute("DELETE FROM jobs")
db.execute("DELETE FROM command_log")
# Tenant-scoped fixture state (no root_id): economic-key ownership and usage
# versions would otherwise make a fresh dossier look like a duplicate (§10.2).
if "usage_registry" in tables:
    db.execute("DELETE FROM usage_registry")
if "usage_versions" in tables:
    db.execute("DELETE FROM usage_versions")
db.commit()
print(f"reset {sys.argv[1]}")
