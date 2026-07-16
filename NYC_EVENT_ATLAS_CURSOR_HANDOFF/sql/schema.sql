PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL,
  parameters_json TEXT NOT NULL,
  manifest_json TEXT
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT,
  authority TEXT NOT NULL,
  confidence TEXT NOT NULL,
  method TEXT NOT NULL,
  refresh_interval TEXT,
  robots_status TEXT,
  last_checked_at TEXT,
  last_success_at TEXT,
  state_json TEXT
);

CREATE TABLE IF NOT EXISTS raw_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  retrieved_at TEXT NOT NULL,
  request_url TEXT NOT NULL,
  request_params_json TEXT,
  http_status INTEGER,
  content_type TEXT,
  etag TEXT,
  last_modified TEXT,
  sha256 TEXT NOT NULL,
  local_path TEXT NOT NULL,
  parser_version TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
  candidate_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES raw_snapshots(snapshot_id),
  source_record_id TEXT,
  source_url TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  normalized_json TEXT,
  extraction_confidence REAL,
  state TEXT NOT NULL DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS event_series (
  series_id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  organizer TEXT,
  first_seen_at TEXT NOT NULL,
  last_verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  series_id TEXT NOT NULL REFERENCES event_series(series_id),
  record_json TEXT NOT NULL,
  occurrence_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
-- occurrence_key is a dedupe aid, not a hard unique identity: the baseline CSV
-- can contain distinct EVENT_IDs that share an occurrence key (e.g. same-day tours).
CREATE INDEX IF NOT EXISTS idx_events_occurrence_key ON events(occurrence_key);

CREATE TABLE IF NOT EXISTS event_sources (
  event_id TEXT NOT NULL REFERENCES events(event_id),
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  snapshot_id TEXT REFERENCES raw_snapshots(snapshot_id),
  source_url TEXT NOT NULL,
  supported_fields_json TEXT,
  confidence TEXT NOT NULL,
  PRIMARY KEY (event_id, source_url)
);

CREATE TABLE IF NOT EXISTS event_updates (
  update_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  verified_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  changes_json TEXT NOT NULL,
  reason TEXT NOT NULL,
  applied_at TEXT
);

CREATE TABLE IF NOT EXISTS review_queue (
  review_id TEXT PRIMARY KEY,
  candidate_id TEXT REFERENCES candidates(candidate_id),
  possible_event_id TEXT REFERENCES events(event_id),
  issue_type TEXT NOT NULL,
  score REAL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidates_state ON candidates(state);
CREATE INDEX IF NOT EXISTS idx_events_series ON events(series_id);
CREATE INDEX IF NOT EXISTS idx_updates_event ON event_updates(event_id);
