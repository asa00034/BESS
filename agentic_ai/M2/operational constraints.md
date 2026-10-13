# Operational Constraints

## Voltage limits

- Nominal acceptable voltage band: **0.95 to 1.05 p.u.**
- Voltage violation condition: `v_min < 0.95` OR `v_max > 1.05`

## SOC bounds

- Expected SOC operating interval: **0.0 to 1.0**
- Operationally preferred SOC interval (policy band): **0.20 to 0.90**

Interpretation:
- If `soc_min < 0.20`, node may be at low-energy risk.
- If `soc_max > 0.90`, node may be near high-energy saturation.

## Smax relationship (tracking quality proxy)

If `Smax` is not directly available, use tracking errors as proxies:
- Active power proxy: `max_abs_error` from `v_dr_power_summary`
- Reactive power proxy: `ABS(mean_q_error)` from `v_voltage_control_summary`

Engineering interpretation:
- Lower tracking error generally implies better adherence to feasible dispatch within converter or inverter limits.
- Larger persistent tracking error can indicate operation near limits (or poor controllability).

## Stable vs vulnerable decision rules

Classify a node in a run as:

### Stable
- `violation_points = 0`
- `soc_min >= 0.20`
- `soc_max <= 0.90`
- `max_abs_error` is low relative to fleet (e.g., below run median)

### Vulnerable
- Any voltage violation (`violation_points > 0`), OR
- SOC outside preferred policy band (`soc_min < 0.20` or `soc_max > 0.90`), OR
- Severe tracking error (e.g., in top quartile of `max_abs_error`)

## Example classification SQL

```sql
SELECT
    v.node_id,
    COALESCE(v.violation_count, 0) AS violation_count,
    s.soc_min,
    s.soc_max,
    d.max_abs_error,
    CASE
        WHEN COALESCE(v.violation_count, 0) > 0 THEN 'vulnerable'
        WHEN s.soc_min < 0.20 OR s.soc_max > 0.90 THEN 'vulnerable'
        ELSE 'stable'
    END AS stability_class
FROM (
    SELECT node_id, COUNT(*) AS violation_count
    FROM v_voltage_violations
    GROUP BY node_id
) v
LEFT JOIN v_soc_summary s
    ON s.node_id = v.node_id
LEFT JOIN (
    SELECT node_id, MAX(abs_error) AS max_abs_error
    FROM v_dr_power_summary
    GROUP BY node_id
) d
    ON d.node_id = v.node_id;
```