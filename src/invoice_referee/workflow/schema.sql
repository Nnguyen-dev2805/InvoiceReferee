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
    -- The employee-confirmed draft (W4): the confirmed field values plus the
    -- original OCR values, as JSON, so a correction is auditable and the
    -- reconciliation can consume the confirmed declaration.
    draft_json TEXT NOT NULL DEFAULT '{}',
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
    -- Role-aware upload (16/10/2026): submitter intent 'paper'|'evidence';
    -- '' = legacy upload without a role (never guessed).
    upload_role TEXT NOT NULL DEFAULT '',
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

-- Validated synthetic demo context (contracts §10.4). budget_amount is retained
-- as legacy metadata; it does not gate current settlement decisions.
CREATE TABLE IF NOT EXISTS context_activities (
    activity_id        TEXT NOT NULL,
    tenant             TEXT NOT NULL,
    name               TEXT NOT NULL,
    occurred_at        TEXT,
    purpose            TEXT NOT NULL,
    budget_amount      INTEGER,
    budget_effect_from TEXT,
    status             TEXT NOT NULL,
    -- Server-owned business profile (T1): TRAVEL or WORK_EXPENSE. Drives the
    -- paper contract refinement; never a client-supplied value.
    profile            TEXT NOT NULL DEFAULT 'TRAVEL',
    -- The namespaced advance/dossier reference(s) this activity is known by
    -- (e.g. "TU-2026-001"). A settlement document that prints one of these can be
    -- linked by DOCUMENT_REFERENCE (14/10/2026). A bare number is not a global id.
    references_json    TEXT NOT NULL DEFAULT '[]',
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
    -- Profiles this grant is valid for (contracts §5, plan R3): a grant for a
    -- different profile never authorizes this activity. Empty = all profiles.
    allowed_profiles_json TEXT NOT NULL DEFAULT '[]',
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

-- Immutable organization-context snapshots (plan A1). The full validated
-- payload is stored verbatim so a restart loads the exact context an assessment
-- rested on; the relational activity/grant/people projection above stays for the
-- existing authorization checks. A new import adds a version; an old snapshot is
-- never overwritten.
CREATE TABLE IF NOT EXISTS context_snapshots (
    tenant      TEXT NOT NULL,
    digest      TEXT NOT NULL,
    version     INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    origin      TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (tenant, digest)
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
    input_basis_json TEXT NOT NULL DEFAULT '{}',
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

-- The typed evidence report for a root (contracts §12.5). Written by the
-- evidence worker after a LIVE/RECORDED_REPLAY read; it is pipeline completion
-- only and is never fed into the finance snapshot.
CREATE TABLE IF NOT EXISTS case_evidence_reports (
    root_id       TEXT PRIMARY KEY REFERENCES cases(id),
    tenant        TEXT NOT NULL,
    report_json   TEXT NOT NULL,
    -- The source digest set + case version the report was read from, so a submit
    -- can reuse a still-valid read instead of re-running OCR (report P1-1/W3).
    input_basis_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

-- A durable, source-bound accountant preview for a received-advance voucher.
-- The PDF itself is in case_sources/uploads; this retains the read and the exact
-- draft later consumed by RecordActual, including source locators across restart.
CREATE TABLE IF NOT EXISTS case_advance_drafts (
    draft_id    TEXT PRIMARY KEY,
    tenant      TEXT NOT NULL,
    root_id     TEXT NOT NULL REFERENCES cases(id),
    source_id   TEXT NOT NULL REFERENCES case_sources(source_id),
    actor       TEXT NOT NULL,
    draft_json  TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Employee-return proof is stored as a pending, source-bound draft. Reading it
-- uses the existing OCR pipeline; no money event is created until accounting
-- confirms the receipt.
CREATE TABLE IF NOT EXISTS case_money_drafts (
    draft_id       TEXT PRIMARY KEY,
    tenant         TEXT NOT NULL,
    root_id        TEXT NOT NULL REFERENCES cases(id),
    instruction_id TEXT NOT NULL,
    source_id      TEXT NOT NULL REFERENCES case_sources(source_id),
    status         TEXT NOT NULL,
    draft_json     TEXT NOT NULL,
    report_json    TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    confirmed_event_id TEXT,
    confirmed_at   TEXT,
    confirmed_by   TEXT,
    UNIQUE (tenant, root_id, source_id, instruction_id)
);
CREATE INDEX IF NOT EXISTS case_money_drafts_pending
    ON case_money_drafts (tenant, root_id, status, created_at);

-- A completed, accountant-bound advance can ground acceptance of exactly this
-- proposed work. It does not change activity status or create an action grant.
CREATE TABLE IF NOT EXISTS case_activity_acceptances (
    acceptance_id       TEXT PRIMARY KEY,
    tenant              TEXT NOT NULL,
    root_id             TEXT NOT NULL REFERENCES cases(id),
    employee            TEXT NOT NULL,
    activity            TEXT NOT NULL,
    advance_external_key TEXT NOT NULL,
    advance_draft_id    TEXT NOT NULL REFERENCES case_advance_drafts(draft_id),
    actor               TEXT NOT NULL,
    accepted_at         TEXT NOT NULL,
    link_basis          TEXT NOT NULL,
    reason              TEXT NOT NULL,
    refs_json           TEXT NOT NULL,
    link_signals_json   TEXT NOT NULL DEFAULT '[]',
    UNIQUE (tenant, root_id, advance_external_key)
);

-- Append-only, accountant-confirmed history coverage. Each record is bound to
-- the root ledger version present at confirmation; a later/backdated event makes
-- it stale without rewriting the record or affecting another dossier.
CREATE TABLE IF NOT EXISTS case_coverage_records (
    coverage_id  TEXT PRIMARY KEY,
    tenant       TEXT NOT NULL,
    root_id      TEXT NOT NULL REFERENCES cases(id),
    ledger_version TEXT NOT NULL,
    coverage_json TEXT NOT NULL,
    actor        TEXT NOT NULL,
    recorded_at  TEXT NOT NULL,
    reason       TEXT NOT NULL
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

-- Digital web-form declarations (S6, 18/10/2026). The employee's typed rows
-- (declaration, not OCR) with per-line evidence mapping. The read builds a
-- synthetic paper from the latest revision; submit re-validates and requires
-- the same canonical hash as the stored read.
CREATE TABLE IF NOT EXISTS case_digital_declarations (
    root_id     TEXT NOT NULL REFERENCES cases(id),
    revision    INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    actor       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (root_id, revision)
);
-- decision persists here (rule/expense/scope/effect/actor/grant/time/refs/reason)
-- so reassessment keeps clearing the covered issues instead of resurrecting
-- them. A refusal is kept with status REFUSED and changes no issue. Facts and
-- actual money are never rewritten by either row.
CREATE TABLE IF NOT EXISTS case_exception_decisions (
    id          TEXT PRIMARY KEY,
    tenant      TEXT NOT NULL,
    root_id     TEXT NOT NULL REFERENCES cases(id),
    rule_id     TEXT NOT NULL,
    expense_ids_json TEXT NOT NULL DEFAULT '[]',
    activity    TEXT NOT NULL,
    max_effect  INTEGER NOT NULL,
    actions_json TEXT NOT NULL DEFAULT '[]',
    actor       TEXT NOT NULL,
    grant_ref   TEXT,
    decided_at  TEXT NOT NULL,
    effect_from TEXT NOT NULL,
    effect_to   TEXT,
    refs_json   TEXT NOT NULL DEFAULT '[]',
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'ACCEPTED'
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


CREATE TABLE IF NOT EXISTS case_authority_decisions (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, root_id TEXT NOT NULL,
 action TEXT NOT NULL, payload_json TEXT NOT NULL, decided_at TEXT NOT NULL,
 FOREIGN KEY(root_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS case_declaration_corrections (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, root_id TEXT NOT NULL,
 source_basis TEXT NOT NULL, payload_json TEXT NOT NULL, observed_at TEXT NOT NULL,
 FOREIGN KEY(root_id) REFERENCES cases(id)
);
