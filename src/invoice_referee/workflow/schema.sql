-- InvoiceReferee workflow schema (contracts §1, §6, §10.2–10.4).
-- Created at T2 with the case/source/session/context tables only; later tasks
-- extend this file (money, jobs, usage, instructions) as they are implemented.

CREATE TABLE IF NOT EXISTS cases (
    id                   TEXT PRIMARY KEY,
    tenant               TEXT NOT NULL,
    employee             TEXT NOT NULL,
    activity             TEXT NOT NULL,
    profile              TEXT NOT NULL,
    state                TEXT NOT NULL,
    version              INTEGER NOT NULL,
    input_revision       INTEGER NOT NULL,
    control_epoch        INTEGER NOT NULL DEFAULT 0,
    activity_name        TEXT NOT NULL,
    activity_occurred_at TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    -- Root unique trong một sandbox: (organization_id, employee_id, activity_id).
    UNIQUE (tenant, employee, activity)
);

CREATE TABLE IF NOT EXISTS case_declarations (
    root_id    TEXT NOT NULL REFERENCES cases(id),
    revision   INTEGER NOT NULL,
    purpose    TEXT NOT NULL,
    notes      TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (root_id, revision)
);

CREATE TABLE IF NOT EXISTS case_sources (
    source_id   TEXT PRIMARY KEY,
    root_id     TEXT NOT NULL REFERENCES cases(id),
    tenant      TEXT NOT NULL,
    filename    TEXT NOT NULL,
    media       TEXT NOT NULL,
    digest      TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    attached_at TEXT NOT NULL
);

-- Command identity=(tenant, actor_id, command_id) + payload fingerprint (§10.3).
CREATE TABLE IF NOT EXISTS command_log (
    tenant      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    command_id  TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    result_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (tenant, actor_id, command_id)
);

CREATE TABLE IF NOT EXISTS demo_sessions (
    session_id TEXT PRIMARY KEY,
    tenant     TEXT NOT NULL,
    persona    TEXT NOT NULL,
    actor_id   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant      TEXT NOT NULL,
    root_id     TEXT,
    session_id  TEXT,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT NOT NULL,
    origin      TEXT NOT NULL DEFAULT 'APP',
    occurred_at TEXT NOT NULL
);

-- Validated synthetic demo context (contracts §10.4). budget_amount NULL means
-- no budget record exists yet; it is never a fabricated zero.
CREATE TABLE IF NOT EXISTS context_activities (
    activity_id        TEXT NOT NULL,
    tenant             TEXT NOT NULL,
    name               TEXT NOT NULL,
    occurred_at        TEXT,
    purpose            TEXT NOT NULL,
    budget_amount      INTEGER,
    budget_effect_from TEXT,
    status             TEXT NOT NULL,
    -- Activity context is per tenant: the same activity id in another tenant
    -- is a separate (proposed) record, never this tenant's catalog entry.
    PRIMARY KEY (tenant, activity_id)
);

CREATE TABLE IF NOT EXISTS context_grants (
    grant_id       TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    version        TEXT NOT NULL,
    actor          TEXT NOT NULL,
    actions_json   TEXT NOT NULL,
    scope          TEXT NOT NULL,
    max_amount     INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    -- Grants are per tenant: the same grant id in another tenant is a
    -- separate record, never an overwrite of this tenant's authority.
    PRIMARY KEY (tenant, grant_id)
);

CREATE TABLE IF NOT EXISTS context_people (
    id     TEXT NOT NULL,
    tenant TEXT NOT NULL,
    name   TEXT NOT NULL,
    -- People are per tenant: an import can never shadow another tenant's name.
    PRIMARY KEY (tenant, id)
);

CREATE TABLE IF NOT EXISTS context_witnesses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    record_key    TEXT NOT NULL,
    quote         TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    UNIQUE (tenant, kind, record_key)
);

CREATE TABLE IF NOT EXISTS context_imports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant      TEXT NOT NULL,
    digest      TEXT NOT NULL,
    origin      TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    note        TEXT NOT NULL
);
