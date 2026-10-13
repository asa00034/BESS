# SQL Templates

Use these patterns to keep generated SQL consistent and safe.

## 1) Voltage violations

### A. Largest voltage deviations
```sql
SELECT ts, node_id, phase, voltage_pu, violation_type, deviation_pu
FROM v_voltage_violations
ORDER BY deviation_pu DESC, ts
LIMIT 20;
```

### B. Under-voltage events only
```sql
SELECT ts, node_id, phase, voltage_pu, deviation_pu
FROM v_voltage_violations
WHERE LOWER(violation_type) IN ('under', 'under_voltage', 'undervoltage')
ORDER BY deviation_pu DESC, ts
LIMIT 50;
```

## 2) SOC summaries

### A. SOC distribution at node level
```sql
SELECT node_id, soc_min, soc_mean, soc_max, sample_count, active_count
FROM v_soc_summary
ORDER BY soc_mean DESC, node_id;
```

### B. Single-node SOC summary
```sql
SELECT node_id, soc_min, soc_mean, soc_max, sample_count, active_count
FROM v_soc_summary
WHERE node_id = :node_id;
```

## 3) Tracking error summaries (active power)

### A. Highest absolute tracking error nodes
```sql
SELECT ts, node_id, p_ref, p_meas, tracking_error, abs_error
FROM v_dr_power_summary
ORDER BY abs_error DESC, ts, node_id
LIMIT 20;
```

### B. Mean tracking error for a single node
```sql
SELECT ts, node_id, p_ref, p_meas, tracking_error, abs_error
FROM v_dr_power_summary
WHERE node_id = :node_id
ORDER BY ts;
```

## 4) Voltage control summary

### A. Reactive power tracking quality
```sql
SELECT ts, node_id, q_meas_a, q_meas_b, q_meas_c, q_ref_a, q_ref_b, q_ref_c, v_a, v_b, v_c, q_violation, v_violation
FROM v_voltage_control_summary
ORDER BY ts DESC, node_id;
```

## 5) Run-level KPI ranking

### A. KPI window overview
```sql
SELECT ts_start, ts_end, total_samples, v_violation_count, q_violation_count, v_min, v_max, mean_abs_dr_error, solve_time_mean_ms, solve_time_max_ms
FROM v_kpi_run_summary
ORDER BY ts_start DESC;
```

## Prompt-side guidance

- `:run_id` and `:node_id` are placeholders in template examples only.
- Final generated SQL should replace placeholders with literals.
- Only include `run_id` predicate when selected view actually has a `run_id` column.
- If user provides a node filter, include `node_id = <node_id>` where supported.