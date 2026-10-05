-- T04 minimal SQLite schema (System §10). JSON payload columns keep this a
-- simple init script rather than an ORM with hundreds of columns. Every
-- statement is idempotent; a numbered migration is added only for a real
-- schema change.
PRAGMA foreign_keys = ON;

-- Schema identity. There is no migration framework; a structural change is a
-- version bump and the repository asserts it on open, telling the operator to
-- recreate the local DB rather than silently running on an incompatible one.
CREATE TABLE IF NOT EXISTS schema_meta (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL
);

-- Structured state/history ---------------------------------------------------

CREATE TABLE IF NOT EXISTS cases (
  id              TEXT PRIMARY KEY,
  case_version    INTEGER NOT NULL,
  workflow_state  TEXT NOT NULL,
  current_run_id  TEXT,
  input_hash      TEXT NOT NULL DEFAULT '',
  claim_json      TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  id             TEXT PRIMARY KEY,
  case_id        TEXT NOT NULL REFERENCES cases(id),
  role           TEXT NOT NULL,
  original_name  TEXT NOT NULL,
  stored_path    TEXT NOT NULL,
  sha256         TEXT NOT NULL,
  mime           TEXT NOT NULL,
  size           INTEGER NOT NULL,
  created_at     TEXT NOT NULL,
  UNIQUE (case_id, sha256)
);

CREATE TABLE IF NOT EXISTS runs (
  id                 TEXT PRIMARY KEY,
  case_id            TEXT NOT NULL REFERENCES cases(id),
  input_hash         TEXT NOT NULL,
  case_version       INTEGER NOT NULL,
  status             TEXT NOT NULL,
  stop_requested     INTEGER NOT NULL DEFAULT 0,
  stage              TEXT NOT NULL,
  started_at         TEXT NOT NULL,
  finished_at        TEXT,
  policy_version     TEXT NOT NULL,
  threshold_version  TEXT NOT NULL,
  identities_json    TEXT NOT NULL DEFAULT '[]',
  result_json        TEXT
);

CREATE TABLE IF NOT EXISTS issues (
  id            TEXT NOT NULL,
  run_id        TEXT NOT NULL REFERENCES runs(id),
  case_id       TEXT NOT NULL REFERENCES cases(id),
  stable_key    TEXT NOT NULL,
  issue_class   TEXT NOT NULL,
  owner_mode    TEXT NOT NULL,
  status        TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  -- An issue id is the stable key of ONE run's decision; the same stable key
  -- recurs across runs (a rerun re-reports it), so identity is (run_id, id).
  PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS human_actions (
  id            TEXT PRIMARY KEY,
  case_id       TEXT NOT NULL REFERENCES cases(id),
  case_version  INTEGER NOT NULL,
  issue_id      TEXT,
  mode          TEXT NOT NULL,
  kind          TEXT NOT NULL,
  reason        TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
  run_id               TEXT PRIMARY KEY REFERENCES runs(id),
  case_id              TEXT NOT NULL REFERENCES cases(id),
  action               TEXT NOT NULL,
  completion_basis     TEXT,
  accepted_amount_vnd  INTEGER,
  technical_code       TEXT,
  payload_json         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_requests (
  id               TEXT PRIMARY KEY,
  case_id          TEXT NOT NULL REFERENCES cases(id),
  run_id           TEXT NOT NULL REFERENCES runs(id),
  payee            TEXT NOT NULL,
  amount_vnd       INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  completion_basis TEXT NOT NULL,
  status           TEXT NOT NULL,
  policy_version   TEXT NOT NULL,
  created_at       TEXT NOT NULL
);

-- At most one current (CREATED) payment request per case. Superseded/revoked
-- rows remain for history so Override can be explained.
CREATE UNIQUE INDEX IF NOT EXISTS one_current_payment_request
  ON payment_requests (case_id) WHERE status = 'CREATED';

CREATE TABLE IF NOT EXISTS events (
  id            TEXT PRIMARY KEY,
  case_id       TEXT,
  run_id        TEXT,
  case_version  INTEGER,
  timestamp     TEXT NOT NULL,
  kind          TEXT NOT NULL,
  stage         TEXT NOT NULL,
  reason        TEXT NOT NULL,
  refs_json     TEXT NOT NULL DEFAULT '[]',
  payload_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS events_case_time ON events (case_id, timestamp);

-- Activated policy survives restart; never silently re-activate an old config.
CREATE TABLE IF NOT EXISTS policy_versions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  version            TEXT NOT NULL,
  config_hash        TEXT NOT NULL,
  activation_id      TEXT,
  threshold_version  TEXT NOT NULL,
  active             INTEGER NOT NULL,
  payload_json       TEXT NOT NULL,
  created_at         TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_policy
  ON policy_versions (active) WHERE active = 1;
