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

-- Persistent jobs (contracts §6, §10.4). A preview/read job has no financial
-- effect; one active job per root. `phase` tracks READING/ASSESSING/DONE.
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    tenant        TEXT NOT NULL,
    root_id       TEXT NOT NULL REFERENCES cases(id),
    kind          TEXT NOT NULL,
    phase         TEXT NOT NULL,
    status        TEXT NOT NULL,
    submit_requested INTEGER NOT NULL DEFAULT 0,
    attempts_json TEXT NOT NULL DEFAULT '{}',
    result_json   TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Cached reads keyed by tenant+source digest+reader config (contracts §6).
-- A cached read is reused across preview/submit on the same basis; a cached
-- decision is never stored here.
CREATE TABLE IF NOT EXISTS read_cache (
    tenant         TEXT NOT NULL,
    source_digest  TEXT NOT NULL,
    reader_config  TEXT NOT NULL,
    result_json    TEXT NOT NULL,
    cached_at      TEXT NOT NULL,
    PRIMARY KEY (tenant, source_digest, reader_config)
);

-- Business issues for a root (contracts §2, §6). Stable id keyed by the
-- recovery key (field/relation/source), not a model-authored name.
CREATE TABLE IF NOT EXISTS case_issues (
    id           TEXT PRIMARY KEY,
    tenant       TEXT NOT NULL,
    root_id      TEXT NOT NULL REFERENCES cases(id),
    kind         TEXT NOT NULL,
    field_or_rule TEXT NOT NULL,
    owner        TEXT NOT NULL,
    status       TEXT NOT NULL,
    recovery_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (root_id, recovery_key)
);

-- Settled conclusions (contracts §10.3). Historical conclusions are kept but
-- superseded; a new revision writes a new row.
CREATE TABLE IF NOT EXISTS case_conclusions (
    id           TEXT PRIMARY KEY,
    tenant       TEXT NOT NULL,
    root_id      TEXT NOT NULL REFERENCES cases(id),
    revision     INTEGER NOT NULL,
    status       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    decided_at   TEXT NOT NULL,
    UNIQUE (root_id, revision)
);

-- Instructions (contracts §4, §10.1). At most one actionable per root.
CREATE TABLE IF NOT EXISTS instructions (
    id               TEXT PRIMARY KEY,
    tenant           TEXT NOT NULL,
    root_id          TEXT NOT NULL REFERENCES cases(id),
    direction        TEXT NOT NULL,
    amount           INTEGER NOT NULL,
    status           TEXT NOT NULL,
    basis            TEXT NOT NULL,
    cost_basis       TEXT NOT NULL,
    authority_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_id    TEXT,
    fulfilled_amount INTEGER NOT NULL DEFAULT 0,
    execution_state  TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

-- Tenant economic usage registry (contracts §10.2). One expense scope has one
-- owner root; a verified obligation is not counted twice across roots.
CREATE TABLE IF NOT EXISTS usage_registry (
    tenant        TEXT NOT NULL,
    economic_key  TEXT NOT NULL,
    owner_root    TEXT NOT NULL,
    expense_id    TEXT NOT NULL,
    payment_keys_json TEXT NOT NULL DEFAULT '[]',
    refs_json     TEXT NOT NULL DEFAULT '[]',
    version       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant, economic_key)
);

-- A STUB hand-transcription for a root (contracts §5). Test/LIVE input only;
-- this is the literal reading the workflow assesses, tagged by data_origin.
CREATE TABLE IF NOT EXISTS case_transcriptions (
    root_id            TEXT PRIMARY KEY REFERENCES cases(id),
    transcription_json TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

-- Responsible confirmations from an owner's answer (contracts §3, §5). A
-- confirmation carries fact/value/actor/scope/reason, never a blanket approval.
-- It feeds the snapshot so an answered FACT changes the basis rather than
-- leaving the recomputed issue OPEN.
CREATE TABLE IF NOT EXISTS case_confirmations (
    id          TEXT PRIMARY KEY,
    tenant      TEXT NOT NULL,
    root_id     TEXT NOT NULL REFERENCES cases(id),
    fact_key    TEXT NOT NULL,
    value       TEXT NOT NULL,
    actor       TEXT NOT NULL,
    scope       TEXT NOT NULL,
    refs_json   TEXT NOT NULL DEFAULT '[]',
    reason      TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE (root_id, fact_key)
);

-- Append-only money ledger (contracts §4, §10.1). A recorded event is never
-- edited or deleted; a reversal is a new linked event. external_key is unique
-- per tenant so a re-sent transaction is not counted twice.
CREATE TABLE IF NOT EXISTS money_events (
    id                 TEXT PRIMARY KEY,
    tenant             TEXT NOT NULL,
    root_id            TEXT NOT NULL REFERENCES cases(id),
    external_key       TEXT NOT NULL,
    kind               TEXT NOT NULL,
    scope              TEXT NOT NULL,
    payer              TEXT NOT NULL,
    payee              TEXT NOT NULL,
    amount             INTEGER NOT NULL,
    event_at           TEXT NOT NULL,
    recorded_at        TEXT NOT NULL,
    verification_state TEXT NOT NULL,
    allocation_state   TEXT NOT NULL,
    reverses_event_id  TEXT,
    payload_json       TEXT NOT NULL,
    UNIQUE (tenant, external_key)
);

-- A demo STUB hand-transcription keyed by activity (contracts §5). Used only
-- when a root has no root-specific transcription (the STUB dev/UI path); it is
-- validated input, not a per-root expected outcome.
CREATE TABLE IF NOT EXISTS context_transcriptions (
    tenant             TEXT NOT NULL,
    activity_id        TEXT NOT NULL,
    transcription_json TEXT NOT NULL,
    PRIMARY KEY (tenant, activity_id)
);
