-- =============================================================================
-- teammate v3 — war-room state schema
-- =============================================================================
-- Apply to Aurora Postgres OR in-cluster Postgres (your choice; Aurora preferred).
-- The chat-api + war-api services connect via POSTGRES_DSN env var.
-- =============================================================================

CREATE TABLE IF NOT EXISTS incidents (
    id                TEXT PRIMARY KEY,
    source            TEXT NOT NULL,            -- auto / eng / cs
    state             TEXT NOT NULL,            -- triage / open / active / resolved / dismissed
    title             TEXT NOT NULL,
    summary           TEXT,
    severity          TEXT DEFAULT 'medium',
    affected_service  TEXT,
    declared_by       TEXT,
    created_at        TIMESTAMPTZ DEFAULT now(),
    resolved_at       TIMESTAMPTZ,
    version           INTEGER NOT NULL DEFAULT 1  -- optimistic locking
);

CREATE INDEX IF NOT EXISTS idx_incidents_state ON incidents (state);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents (created_at DESC);


-- Per-incident timeline: alerts, chat messages, action toggles, state changes
CREATE TABLE IF NOT EXISTS incident_events (
    id            BIGSERIAL PRIMARY KEY,
    incident_id   TEXT NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL,                -- chat / action_toggle / state_change / mirror / alert
    actor         TEXT,
    payload       JSONB,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_incident ON incident_events (incident_id, created_at);


-- Participants who joined the war-room
CREATE TABLE IF NOT EXISTS incident_participants (
    incident_id   TEXT NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    role          TEXT DEFAULT 'engineer',      -- engineer / lead / observer
    joined_at     TIMESTAMPTZ DEFAULT now(),
    left_at       TIMESTAMPTZ,
    client_agent_active  BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (incident_id, user_id)
);


-- Slack DMs sent for participant proposals (idempotent fan-out)
CREATE TABLE IF NOT EXISTS slack_dms_sent (
    incident_id   TEXT NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    dm_ts         TEXT,
    sent_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (incident_id, user_id)
);


-- Auto-pre-load results
CREATE TABLE IF NOT EXISTS incident_preload (
    incident_id        TEXT PRIMARY KEY REFERENCES incidents (id) ON DELETE CASCADE,
    summary            TEXT,
    similar_incidents  JSONB,
    candidate_causes   JSONB,
    runbooks           JSONB,
    actions            JSONB,
    participants       JSONB,
    live_data_urls     JSONB,
    generated_at       TIMESTAMPTZ DEFAULT now()
);


-- LLM-learned patterns (for v3+ optional pattern layer)
CREATE TABLE IF NOT EXISTS patterns (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    precursor     TEXT,                          -- e.g. "CPU saturation 5m before 5xx spike"
    evidence_incidents JSONB,                    -- list of incident_ids that exhibited this pattern
    confidence    REAL,
    approved      BOOLEAN DEFAULT FALSE,         -- human-in-the-loop required
    created_at    TIMESTAMPTZ DEFAULT now(),
    approved_at   TIMESTAMPTZ,
    approved_by   TEXT
);


-- Watchlist sync state (which rules are currently applied to SigNoz)
CREATE TABLE IF NOT EXISTS watchlist_sync (
    rule_name     TEXT PRIMARY KEY,
    signoz_rule_id TEXT,
    last_synced   TIMESTAMPTZ DEFAULT now(),
    yaml_hash     TEXT
);
