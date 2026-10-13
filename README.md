# LLM-Based Monitoring Copilot

This repository implements an end-to-end workflow where a language model turns an operator question into SQL, executes that SQL on PostgreSQL, evaluates operating constraints, and returns a grounded final answer.

## Workflow Architecture

1. SQL generation from natural language:
   `llm generate sql.py` (wrapper) -> `pipeline/sql_generator.py`
2. SQL execution and packaging:
   `run sql.py` (wrapper) -> `pipeline/sql_runner.py`
3. Constraint classification:
   `constraint check.py` (wrapper) -> `pipeline/constraint_checker.py`
4. End-to-end orchestration:
   `answer pipeline.py` (wrapper) -> `pipeline/answering_pipeline.py`
5. Optional report view:
   `scripts/generate_output_summary.py` -> HTML summary

Architecture diagrams (components + data flow):

- `docs/grid-copilot-system-architecture.md`

LLM context package used at query time:

- `agentic_ai/M2/schema for llm.md`
- `agentic_ai/M2/sql templates.md`
- `agentic_ai/M2/id mapping.json`
- `agentic_ai/M2/operational constraints.md`

## Reproducible Setup

1. Activate environment

```powershell
& .\.venv\Scripts\Activate.ps1
```

2. Create/refresh DB objects

```bash
psql "postgresql://postgres:YOUR_PASSWORD@localhost:5432/postgres" -f sql/schema.sql
psql "postgresql://postgres:YOUR_PASSWORD@localhost:5432/postgres" -f sql/views.sql
```

3. Optional environment variables

- `OPENAI_API_KEY` for LLM response generation
- `DATABASE_URL` for PostgreSQL credentials and connection settings. Put it in your ignored `.env` file or set it in your shell; the source code contains no database password.

## How To Run Case Study Pipeline

Run all three case-study questions:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "answer pipeline.py" --case-study --run-id "run_2026_02_13"
```

Run case-study questions from a JSON file (`id` + `question`):

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "answer pipeline.py" --case-study --run-id "run_2026_02_13" --questions-file "agentic_ai/M2/test_questions_v1.json"
```

Expected output files for this JSON format:

- `outputs/final answers/q1.json`
- `outputs/final answers/q2.json`
- `outputs/final answers/q3.json`

Run one custom question:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "answer pipeline.py" --run-id "run_2026_02_13" --question-id "q_custom_1" --question "For this run, summarize SOC by node and highlight the lowest SOC nodes."
```

Generate simple HTML summary:

```powershell
python scripts/generate_output_summary.py
```

Sample report output for `run_2026_02_13`:

| Total questions | Stable | Vulnerable | Unstable | Constrained | Unknown |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 2 | 1 | 0 | 0 | 0 |

**q1 - stable**

**Question:** Voltage stability duration assessment. For Run run_2026_02_13, how long was Node 25 within the acceptable voltage range (0.95-1.05 pu), and how long was it outside that range?

**Rows:** 1 | **Execution ms:** 190.48

> For run_2026_02_13, Node 25 was within the acceptable 0.95–1.05 pu range for 0 samples and outside the range for 1962 samples. Interpreting samples as equal-duration timesteps, that means 0 timestep-duration in-range and 1962 timestep-durations out-of-range over the assessed period. The condition label is stable. This result suggests a data/scoping issue (e.g., the view may already contain only violations or may not be filtered to Node 25/run_2026_02_13), because an all-outside outcome conflicts with “no major violations.” Recommendation: re-run the query against the full voltage time series filtered by run and node, and compute durations using the actual timestep (or timestamps) rather than raw sample counts.

**q2 - vulnerable**

**Question:** Identification of most voltage-vulnerable nodes. Across all monitored buses in Run run_2026_02_13, which node experienced the most severe voltage violations based on count and total duration?

**Rows:** 1 | **Execution ms:** 213.65

> Across all monitored buses in run_2026_02_13, node 86 experienced the most severe voltage violations by both count and duration. It recorded 675 violation events with a total violation window of 0 days 00:08:18. The aggregated deviation was -1.18154 pu, indicating predominantly undervoltage behavior, while the maximum deviation observed in this result set was 0.0 pu. Based on these indicators, the condition label is vulnerable. Recommendation: prioritize node 86 for mitigation by checking local voltage support capability (e.g., inverter VAR settings, capacitor control, or tap changer coordination) and validating the underlying load/DER modeling around that bus.

**q3 - stable**

**Question:** Reactive power overshoot and voltage impact. At Node 25 during Run run_2026_02_13, did reactive power injection overshoot the reference value, and did overshoot coincide with voltage oscillations or repeated voltage excursions?

**Rows:** 2 | **Execution ms:** 205.35

> At Node 25 in run_2026_02_13, reactive power injection did overshoot the reference, but only slightly and briefly. At ts=1970-01-01 00:00:02+00:00, Phase A showed a positive tracking error of +0.00358 (max_abs_q_tracking_error=0.00358), while other phases were essentially zero. This small overshoot did not coincide with voltage oscillations or repeated excursions; the voltage change was a single-step increase on v_a of dv_a=+0.00439 (0.94273 to 0.94712 pu) with no evidence of back-and-forth behavior given only two samples. Both timestamps show an under-voltage on Phase A (0.94273 pu and 0.94712 pu), indicating a mild but persistent low-voltage condition rather than oscillatory instability. Condition label: stable. Recommendation: extend the time window and sampling (more than 2 points) and add an overshoot threshold (e.g., flag >0.01 pu-equivalent Q error) to confirm whether this is benign tracking noise or a repeatable control transient near the undervoltage boundary.

## Example Commands and Expected Outputs

Generate SQL only:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "llm generate sql.py" --run-id "run_2026_02_13" --question "Which nodes have the highest voltage violations?"
```

Expected output:

- SQL draft in `logs/sql drafts/*.sql`

Execute SQL only:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "run sql.py" --sql-file "logs/sql drafts/<file>.sql" --question-id "demo_q"
```

Expected output:

- `outputs/sql results/demo_q.json`
- `outputs/sql results/demo_q.meta.json`

Run constraint check only:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "constraint check.py" --input "outputs/sql results/demo_q.json" --question-id "demo_q"
```

Expected output:

- `outputs/constraint checks/demo_q.decision.json`

Run end-to-end once:

```powershell
C:/Users/Azmee/my_python_project/.venv/Scripts/python.exe "answer pipeline.py" --run-id "run_2026_02_13" --question-id "single_q" --question "For this run, summarize active-power tracking error and rank nodes by max absolute error."
```

Expected output:

- `outputs/final answers/single_q.json`
- `outputs/sql results/single_q.json`
- `outputs/constraint checks/single_q.decision.json`

## Folder Structure (Portfolio Packaging)

```text
agentic_ai/M2/
  schema for llm.md
  sql templates.md
  id mapping.json
  operational constraints.md
pipeline/
  sql_generator.py
  sql_runner.py
  constraint_checker.py
  answering_pipeline.py
logs/
  sql drafts/
  refinement.json
outputs/
  sql results/
  constraint checks/
  final answers/
   HTML summary
manual sql validation.md
```

## Grafana Screenshot Mapping

Add screenshots under `docs/screenshots/`:

- `docs/screenshots/grafana_voltage_violations.png`
- `docs/screenshots/grafana_soc_summary.png`
- `docs/screenshots/grafana_tracking_error.png`

Map each screenshot to SQL evidence:

1. `grafana_voltage_violations.png`
   - SQL: `outputs/sql results/case_study_q1.json`
   - Constraint: `outputs/constraint checks/case_study_q1.decision.json`
2. `grafana_soc_summary.png`
   - SQL: `outputs/sql results/case_study_q2.json`
   - Constraint: `outputs/constraint checks/case_study_q2.decision.json`
3. `grafana_tracking_error.png`
   - SQL: `outputs/sql results/case_study_q3.json`
   - Constraint: `outputs/constraint checks/case_study_q3.decision.json`

Suggested caption template:

`Question -> SQL file -> row_count -> constraint_label -> key numeric finding`
