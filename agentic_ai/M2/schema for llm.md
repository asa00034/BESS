# Schema for LLM

This file defines the **only allowed SQL sources** for LLM-generated SQL.

## Allowed views

1. `v_voltage_violations`
2. `v_soc_summary`
3. `v_dr_power_summary`
4. `v_voltage_control_summary`
5. `v_kpi_run_summary`

## View columns, units, and meanings

The following definitions are aligned with the current live PostgreSQL views.

### `v_voltage_violations`
- `ts` (timestamp): timestamp of observation.
- `node_id` (integer): node identifier in the network.
- `phase` (text): phase label (A/B/C) where violation was recorded.
- `voltage_pu` (p.u.): measured per-unit voltage.
- `violation_type` (text): violation category such as under-voltage or over-voltage.
- `deviation_pu` (p.u.): magnitude of deviation from voltage threshold.

Example:
```sql
SELECT ts, node_id, phase, voltage_pu, violation_type, deviation_pu
FROM v_voltage_violations
ORDER BY deviation_pu DESC, ts
LIMIT 10;
```

### `v_soc_summary`
- `node_id` (integer): node identifier in the network.
- `soc_min` (fraction, 0-1): minimum state of charge.
- `soc_mean` (fraction, 0-1): average state of charge.
- `soc_max` (fraction, 0-1): maximum state of charge.
- `sample_count` (count): total count of SOC records included.
- `active_count` (count): count of SOC records flagged active by view logic.

Example:
```sql
SELECT node_id, soc_min, soc_mean, soc_max, sample_count, active_count
FROM v_soc_summary
ORDER BY soc_mean DESC, node_id
LIMIT 10;
```

### `v_dr_power_summary`
- `ts` (timestamp): timestamp of observation.
- `node_id` (integer): node identifier in the network.
- `p_ref` (power units): requested or reference active power.
- `p_meas` (power units): measured active power.
- `tracking_error` (power units): signed tracking error (`p_meas - p_ref`).
- `abs_error` (power units): absolute tracking error.

Example:
```sql
SELECT ts, node_id, p_ref, p_meas, tracking_error, abs_error
FROM v_dr_power_summary
ORDER BY abs_error DESC, ts
LIMIT 10;
```

### `v_voltage_control_summary`
- `ts` (timestamp): timestamp of observation.
- `node_id` (integer): node identifier in the network.
- `q_meas_a`, `q_meas_b`, `q_meas_c` (reactive power units): measured phase reactive power.
- `q_ref_a`, `q_ref_b`, `q_ref_c` (reactive power units): reference phase reactive power.
- `v_a`, `v_b`, `v_c` (p.u.): phase voltage magnitudes.
- `q_violation` (boolean/flag): reactive control violation indicator.
- `v_violation` (boolean/flag): voltage control violation indicator.

Example:
```sql
SELECT ts, node_id, q_meas_a, q_meas_b, q_meas_c, q_ref_a, q_ref_b, q_ref_c, v_a, v_b, v_c, q_violation, v_violation
FROM v_voltage_control_summary
ORDER BY ts DESC, node_id
LIMIT 10;
```

### `v_kpi_run_summary`
- `ts_start` (timestamp): first telemetry timestamp in KPI window.
- `ts_end` (timestamp): last telemetry timestamp in KPI window.
- `total_samples` (count): total telemetry sample count in window.
- `v_violation_count` (count): number of voltage-violation events.
- `v_min` (p.u.): minimum observed voltage across run window.
- `v_max` (p.u.): maximum observed voltage across run window.
- `q_violation_count` (count): number of reactive control violations.
- `fes_mean` (unit depends on source metric): average `fes` value.
- `mean_abs_dr_error` (power units): mean absolute DR tracking error.
- `solve_time_mean_ms` (ms): mean solver time.
- `solve_time_max_ms` (ms): max solver time.
- `switch_flag_count` (count): number of switch-flag events.

Example:
```sql
SELECT ts_start, ts_end, total_samples, v_violation_count, v_min, v_max, q_violation_count, mean_abs_dr_error
FROM v_kpi_run_summary
ORDER BY ts_start DESC
LIMIT 10;
```

## LLM SQL safety rules

- Only generate a **single `SELECT` query**.
- Do not reference base tables (`telemetry`, `runs`, `events`) in generated SQL.
- Do not use DDL/DML (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`).
- Prefer explicit column selection over `SELECT *` unless user asks for full detail.
- If `run_id` is not available in a view schema, do not force a `run_id` predicate.