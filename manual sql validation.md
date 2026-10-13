# Manual SQL Validation

Date: 2026-03-09

## Validation method

- SQL generated via `llm generate sql.py` in manual validation mode.
- Context files used:
  - `agentic_ai/M2/schema for llm.md`
  - `agentic_ai/M2/sql templates.md`
  - `agentic_ai/M2/id mapping.json`
- Generated SQL files saved under `logs/sql drafts/`.
- Queries executed manually against PostgreSQL and checked for:
  1. Syntax correctness
  2. Expected result columns
  3. Non-empty/meaningful row counts

## Final working prompt pattern

The final successful prompt used this structure (programmatically filled):

```text
You are generating PostgreSQL SQL in MANUAL VALIDATION MODE.

Objective:
- Return exactly one SQL query string.
- The query must answer the user question.

Hard constraints:
1) Use ONLY these views: v_dr_power_summary, v_kpi_run_summary, v_soc_summary, v_voltage_control_summary, v_voltage_violations
2) Do not use base tables.
3) Output SQL only (no explanation, no markdown fences).
4) Use run_id = '<run_id>' only for views that contain a run_id column.
5) If node filter is provided, include node_id = <node_id>.

[schema for llm.md content]
[sql templates.md content]
[id mapping.json content]
[detected live view columns]

Question: <question>
Run filter: <run_id>
Node filter: <optional node_id>
```

---

## Case study 1

**Question**
Which nodes have the highest voltage violations?

**Final SQL (working)**
```sql
SELECT
  node_id,
  COUNT(*) AS violation_count,
  MAX(deviation_pu) AS max_deviation_pu,
  AVG(deviation_pu) AS mean_deviation_pu
FROM v_voltage_violations
GROUP BY node_id
ORDER BY violation_count DESC, max_deviation_pu DESC, node_id
LIMIT 20
```

**Validation note**
- Status: Correct.
- Returned columns: `node_id`, `violation_count`, `max_deviation_pu`, `mean_deviation_pu`.
- Row count observed: 9.
- Engineering meaning: correctly ranks nodes by frequency and severity of voltage violations.

## Case study 2

**Question**
Summarize SOC by node and highlight the lowest SOC nodes.

**Final SQL (working)**
```sql
SELECT
  node_id,
  soc_min,
  soc_mean,
  soc_max,
  sample_count,
  active_count
FROM v_soc_summary
ORDER BY soc_min ASC, soc_mean ASC, node_id
LIMIT 20
```

**Validation note**
- Status: Correct.
- Returned columns: `node_id`, `soc_min`, `soc_mean`, `soc_max`, `sample_count`, `active_count`.
- Row count observed: 10.
- Engineering meaning: correctly highlights nodes with lowest SOC values first while preserving summary metrics.

## Case study 3

**Question**
Summarize active-power tracking error and rank nodes by max absolute error.

**Final SQL (working)**
```sql
SELECT
  node_id,
  MAX(abs_error) AS max_abs_error,
  AVG(abs_error) AS mean_abs_error,
  AVG(tracking_error) AS mean_signed_error,
  COUNT(*) AS sample_count
FROM v_dr_power_summary
GROUP BY node_id
ORDER BY max_abs_error DESC, mean_abs_error DESC, node_id
```

**Validation note**
- Status: Correct.
- Returned columns: `node_id`, `max_abs_error`, `mean_abs_error`, `mean_signed_error`, `sample_count`.
- Row count observed: 10.
- Engineering meaning: correctly ranks nodes by worst tracking error magnitude and provides average error context.