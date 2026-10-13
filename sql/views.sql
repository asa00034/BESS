CREATE OR REPLACE VIEW v_voltage_violations AS
WITH typed AS (
    SELECT
        run_id,
        ts::timestamptz AS ts,
        node_id::int AS node_id,
        NULLIF(v_bus_pu, '')::double precision AS v_bus_pu
    FROM telemetry_iot_raw
),
phases AS (
    SELECT run_id, ts, node_id, 'a'::text AS phase, v_bus_pu AS voltage_pu FROM typed
    UNION ALL
    SELECT run_id, ts, node_id, 'b'::text AS phase, v_bus_pu AS voltage_pu FROM typed
    UNION ALL
    SELECT run_id, ts, node_id, 'c'::text AS phase, v_bus_pu AS voltage_pu FROM typed
)
SELECT
    run_id,
    ts,
    node_id,
    phase,
    voltage_pu,
    CASE
        WHEN voltage_pu < 0.95 THEN 'undervoltage'
        WHEN voltage_pu > 1.05 THEN 'overvoltage'
        ELSE NULL
    END AS violation_type,
    CASE
        WHEN voltage_pu < 0.95 THEN 0.95 - voltage_pu
        WHEN voltage_pu > 1.05 THEN voltage_pu - 1.05
        ELSE 0
    END AS deviation_pu
FROM phases
WHERE voltage_pu IS NOT NULL
  AND (voltage_pu < 0.95 OR voltage_pu > 1.05);

CREATE OR REPLACE VIEW v_soc_summary AS
SELECT
    run_id,
    node_id::int AS node_id,
    MIN(NULLIF(soc_percent, '')::double precision) AS soc_min,
    AVG(NULLIF(soc_percent, '')::double precision) AS soc_mean,
    MAX(NULLIF(soc_percent, '')::double precision) AS soc_max,
    COUNT(*) AS sample_count,
    COUNT(*) FILTER (WHERE NULLIF(dr_event_flag, '')::int = 1) AS active_count
FROM telemetry_iot_raw
GROUP BY run_id, node_id;

CREATE OR REPLACE VIEW v_dr_power_summary AS
SELECT
    run_id,
    ts::timestamptz AS ts,
    node_id::int AS node_id,
    NULLIF(p_ref_kw, '')::double precision AS p_ref,
    NULLIF(p_meas_kw, '')::double precision AS p_meas,
    (NULLIF(p_meas_kw, '')::double precision - NULLIF(p_ref_kw, '')::double precision) AS tracking_error,
    ABS(NULLIF(p_meas_kw, '')::double precision - NULLIF(p_ref_kw, '')::double precision) AS abs_error
FROM telemetry_iot_raw;

CREATE OR REPLACE VIEW v_voltage_control_summary AS
SELECT
    run_id,
    ts::timestamptz AS ts,
    node_id::int AS node_id,
    NULLIF(q_meas_kvar, '')::double precision AS q_meas_a,
    NULLIF(q_meas_kvar, '')::double precision AS q_meas_b,
    NULLIF(q_meas_kvar, '')::double precision AS q_meas_c,
    NULLIF(q_ref_kvar, '')::double precision AS q_ref_a,
    NULLIF(q_ref_kvar, '')::double precision AS q_ref_b,
    NULLIF(q_ref_kvar, '')::double precision AS q_ref_c,
    NULLIF(v_bus_pu, '')::double precision AS v_a,
    NULLIF(v_bus_pu, '')::double precision AS v_b,
    NULLIF(v_bus_pu, '')::double precision AS v_c,
    (ABS(NULLIF(q_meas_kvar, '')::double precision - NULLIF(q_ref_kvar, '')::double precision) > 0.5) AS q_violation,
    (NULLIF(v_bus_pu, '')::double precision < 0.95 OR NULLIF(v_bus_pu, '')::double precision > 1.05) AS v_violation
FROM telemetry_iot_raw;

CREATE OR REPLACE VIEW v_kpi_run_summary AS
WITH typed AS (
    SELECT
        run_id,
        ts::timestamptz AS ts,
        node_id::int AS node_id,
        NULLIF(v_bus_pu, '')::double precision AS v_bus_pu,
        NULLIF(q_meas_kvar, '')::double precision AS q_meas_kvar,
        NULLIF(q_ref_kvar, '')::double precision AS q_ref_kvar,
        NULLIF(p_meas_kw, '')::double precision AS p_meas_kw,
        NULLIF(p_ref_kw, '')::double precision AS p_ref_kw,
        NULLIF(resilience_score_slnr, '')::double precision AS fes_node,
        NULLIF(latency_ms, '')::double precision AS solve_time_ms,
        NULLIF(voltage_violation_flag, '')::int AS switch_flag
    FROM telemetry_iot_raw
)
SELECT
    run_id,
    MIN(ts) AS ts_start,
    MAX(ts) AS ts_end,
    COUNT(*) AS total_samples,
    COUNT(*) FILTER (WHERE v_bus_pu < 0.95 OR v_bus_pu > 1.05) AS v_violation_count,
    MIN(v_bus_pu) AS v_min,
    MAX(v_bus_pu) AS v_max,
    COUNT(*) FILTER (WHERE ABS(q_meas_kvar - q_ref_kvar) > 0.5) AS q_violation_count,
    AVG(fes_node) AS fes_mean,
    AVG(ABS(p_meas_kw - p_ref_kw)) AS mean_abs_dr_error,
    AVG(solve_time_ms) AS solve_time_mean_ms,
    MAX(solve_time_ms) AS solve_time_max_ms,
    SUM(COALESCE(switch_flag, 0)) AS switch_flag_count
FROM typed
GROUP BY run_id;
