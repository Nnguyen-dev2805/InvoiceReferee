-- Settlement MVP schema (System §S7): eight tables, typed JSON payloads.
-- Commands live in audit_events; the partial unique index is the idempotency
-- guard scoped by (operation, actor, case scope, key).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    case_version INTEGER NOT NULL CHECK (case_version >= 1),
    input_revision INTEGER NOT NULL CHECK (input_revision >= 1),
    control_epoch INTEGER NOT NULL CHECK (control_epoch >= 1),
    stop_active INTEGER NOT NULL CHECK (stop_active IN (0, 1)),
    stage TEXT NOT NULL,
    current_run_id TEXT,
    submission_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_revisions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    revision INTEGER NOT NULL,
    submission_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    command_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (case_id, revision)
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    supersedes_source_id TEXT REFERENCES sources(id),
    uploader_actor_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    original_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    input_revision INTEGER NOT NULL,
    control_epoch INTEGER NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    report_json TEXT,
    detail TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL CHECK (kind IN ('QUESTION', 'RESPONSE', 'REVIEW')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS money_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    operation TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    command_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS audit_events_command_key
    ON audit_events (operation, actor_id, scope_key, command_key);
