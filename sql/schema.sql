-- Active: 1770269215335@@localhost@5432@postgres
BEGIN;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario TEXT,
    csv_path TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_count BIGINT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS telemetry (
    "time" DOUBLE PRECISION,
    node_id BIGINT,
    v_a DOUBLE PRECISION,
    v_b DOUBLE PRECISION,
    v_c DOUBLE PRECISION,
    q_a DOUBLE PRECISION,
    q_b DOUBLE PRECISION,
    q_c DOUBLE PRECISION,
    dv_a DOUBLE PRECISION,
    dv_b DOUBLE PRECISION,
    dv_c DOUBLE PRECISION,
    dq_a DOUBLE PRECISION,
    dq_b DOUBLE PRECISION,
    dq_c DOUBLE PRECISION,
    f_node DOUBLE PRECISION,
    fes_node DOUBLE PRECISION,
    solve_time_ms DOUBLE PRECISION,
    switch_flag INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL,
    node_id INTEGER,
    event_type TEXT NOT NULL,
    severity TEXT,
    details JSONB
);



CREATE INDEX IF NOT EXISTS telemetry_time_idx ON telemetry ("time");
CREATE INDEX IF NOT EXISTS telemetry_node_time_idx ON telemetry (node_id, "time");

COMMIT;
