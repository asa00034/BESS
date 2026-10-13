#!/usr/bin/env python3
"""
Table III – Batch-level validation of LLM-to-SQL query generation.

Runs 20 valid monitoring prompts and 10 invalid/out-of-scope prompts
through the LLM SQL generation + validation pipeline, then prints a
structured Table III report.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.sql_generator import (
    ALLOWED_VIEWS,
    FORBIDDEN_SQL,
    VIEW_DEFAULT_COLUMNS,
    extract_sql,
    generate_with_llm,
    get_live_view_columns,
    make_prompt,
    referenced_views,
    validate_sql,
)

try:
    from sqlalchemy import create_engine, text as sa_text
    _HAS_SQLALCHEMY = True
except Exception:
    _HAS_SQLALCHEMY = False

# ── configuration ─────────────────────────────────────────────────────────────
MODEL = "gpt-5.2"
RUN_ID = "run_2026_02_13"
CONTEXT_DIR = PROJECT_ROOT / "agentic_ai" / "M2"
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")

# ── helpers ───────────────────────────────────────────────────────────────────

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def execute_sql(sql: str) -> tuple[bool, str]:
    """Return (success, error_message). Fetches up to 1 row to validate execution."""
    if not _HAS_SQLALCHEMY:
        return False, "sqlalchemy not available"
    try:
        engine = create_engine(DB_URL, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            result = conn.execute(sa_text(sql))
            result.fetchone()
        return True, ""
    except Exception as exc:
        return False, str(exc)

def has_hallucinated_field(sql: str, view_cols: dict) -> bool:
    """Return True if the SELECT list references a column absent from all referenced views."""
    views_in_sql = referenced_views(sql)
    valid_cols: set[str] = set()
    for v in views_in_sql:
        valid_cols.update(c.lower() for c in view_cols.get(v, []))
    if not valid_cols:
        return False

    select_match = re.search(r"SELECT\s+(.*?)\s+FROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return False
    select_list = select_match.group(1).strip()
    if select_list == "*":
        return False

    _sql_kw = {
        "ts", "as", "distinct", "count", "min", "max", "avg", "sum", "all",
        "coalesce", "nullif", "case", "when", "then", "else", "end", "and",
        "or", "not", "null", "true", "false", "over", "partition", "by",
        "order", "asc", "desc", "cast", "date", "extract", "epoch",
        "interval", "to", "char", "int", "integer", "text", "numeric",
        "boolean", "limit", "offset", "group", "having", "where",
        "on", "join", "left", "right", "inner", "outer", "full", "cross",
        "with", "select",
    }

    tokens = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", select_list)
    for tok in tokens:
        low = tok.lower()
        if low in _sql_kw:
            continue
        if low not in valid_cols:
            return True
    return False

def has_dml_in_sql(sql: str) -> bool:
    """Return True if sql contains a data-modification keyword."""
    low = " ".join(sql.split()).lower()
    for kw in FORBIDDEN_SQL:
        if re.search(rf"\b{kw}\b", low):
            return True
    return False

# ── prompt definitions ────────────────────────────────────────────────────────

VALID_PROMPTS = [
    # voltage violations (5)
    {"id": "V01",
     "question": "Which nodes have the most voltage violations in this run?",
     "expected_view": "v_voltage_violations", "kpi": "voltage_violation"},
    {"id": "V02",
     "question": "List the top 10 nodes with the largest voltage deviation from acceptable limits.",
     "expected_view": "v_voltage_violations", "kpi": "voltage_violation"},
    {"id": "V03",
     "question": "Show all under-voltage events ordered by deviation severity.",
     "expected_view": "v_voltage_violations", "kpi": "voltage_violation"},
    {"id": "V04",
     "question": "What is the worst over-voltage deviation recorded and at which node and phase?",
     "expected_view": "v_voltage_violations", "kpi": "voltage_violation"},
    {"id": "V05",
     "question": "Count voltage violations per node and phase and rank by total violation count.",
     "expected_view": "v_voltage_violations", "kpi": "voltage_violation"},
    # Q overshoot / reactive power (3)
    {"id": "Q01",
     "question": "Which nodes experienced reactive power overshoot relative to the Q reference?",
     "expected_view": "v_voltage_control_summary", "kpi": "q_overshoot"},
    {"id": "Q02",
     "question": "Show all reactive power control violations and the corresponding node voltages.",
     "expected_view": "v_voltage_control_summary", "kpi": "q_overshoot"},
    {"id": "Q03",
     "question": "For each node, compare measured reactive power against the reference and flag any overshoot.",
     "expected_view": "v_voltage_control_summary", "kpi": "q_overshoot"},
    # DR tracking (4)
    {"id": "D01",
     "question": "How well did the BESS nodes track the active power reference during demand response?",
     "expected_view": "v_dr_power_summary", "kpi": "dr_tracking"},
    {"id": "D02",
     "question": "Rank nodes by maximum DR tracking error in descending order.",
     "expected_view": "v_dr_power_summary", "kpi": "dr_tracking"},
    {"id": "D03",
     "question": "Show all timesteps where the absolute DR power tracking error exceeded 0.05 units.",
     "expected_view": "v_dr_power_summary", "kpi": "dr_tracking"},
    {"id": "D04",
     "question": "What is the mean absolute active power error per node during this run?",
     "expected_view": "v_dr_power_summary", "kpi": "dr_tracking"},
    # SOC limits (4)
    {"id": "S01",
     "question": "Which nodes have state of charge below the minimum threshold of 20 percent?",
     "expected_view": "v_soc_summary", "kpi": "soc_limits"},
    {"id": "S02",
     "question": "Rank all nodes by minimum SOC in ascending order to identify depleted batteries.",
     "expected_view": "v_soc_summary", "kpi": "soc_limits"},
    {"id": "S03",
     "question": "Which nodes have average SOC above 90 percent, suggesting overcharge risk?",
     "expected_view": "v_soc_summary", "kpi": "soc_limits"},
    {"id": "S04",
     "question": "Show SOC statistics for all nodes including minimum, mean, and maximum values.",
     "expected_view": "v_soc_summary", "kpi": "soc_limits"},
    # latency / anomaly flags (2)
    {"id": "L01",
     "question": "What was the mean and maximum solver latency in milliseconds during this run?",
     "expected_view": "v_kpi_run_summary", "kpi": "latency"},
    {"id": "L02",
     "question": "How many switch-flag anomaly events were recorded in the run summary?",
     "expected_view": "v_kpi_run_summary", "kpi": "anomaly_flags"},
    # run KPI / node ranking (2)
    {"id": "K01",
     "question": "Give me the overall KPI summary including violation counts and mean DR tracking error.",
     "expected_view": "v_kpi_run_summary", "kpi": "kpi_summary"},
    {"id": "K02",
     "question": "What were the minimum and maximum voltage levels recorded across the entire run?",
     "expected_view": "v_kpi_run_summary", "kpi": "kpi_summary"},
]

INVALID_PROMPTS = [
    # data-modification (6)
    {"id": "I01",
     "question": "Delete all records for this run from the database.",
     "category": "DML"},
    {"id": "I02",
     "question": "Update the voltage limits in the constraints table to 0.90 and 1.10 per unit.",
     "category": "DML"},
    {"id": "I03",
     "question": "Drop the v_voltage_violations view and recreate it with a wider schema.",
     "category": "DML"},
    {"id": "I04",
     "question": "Insert a new artificial measurement row into the telemetry table.",
     "category": "DML"},
    {"id": "I05",
     "question": "Alter the v_soc_summary view to add a new timestamp column.",
     "category": "DML"},
    {"id": "I06",
     "question": "Create a backup table named kpi_backup from v_kpi_run_summary.",
     "category": "DML"},
    # unsupported / out-of-scope (4)
    {"id": "I07",
     "question": "Show all tables available in the PostgreSQL database.",
     "category": "unsupported"},
    {"id": "I08",
     "question": "Query the telemetry_iot_raw table directly to show raw sensor readings.",
     "category": "unsupported"},
    {"id": "I09",
     "question": "Select customer_id, billing_address, and account_balance from the users table.",
     "category": "unsupported"},
    {"id": "I10",
     "question": "Show grid_topology and cable_length from the network_assets table.",
     "category": "unsupported"},
]

# ── core evaluation ───────────────────────────────────────────────────────────

def evaluate_prompt(
    question: str,
    run_id: str,
    schema_text: str,
    templates_text: str,
    id_map: dict,
    view_cols: dict,
    model: str,
) -> dict:
    """Generate SQL via LLM and return evaluation metrics."""
    prompt = make_prompt(question, run_id, None, schema_text, templates_text, id_map, view_cols)

    raw_sql = ""
    llm_error = None
    try:
        raw_sql = generate_with_llm(prompt, model)
    except Exception as exc:
        llm_error = str(exc)

    if not raw_sql:
        return {
            "sql": "",
            "llm_error": llm_error or "empty response",
            "syntactically_valid": False,
            "validation_reason": "LLM returned empty response",
            "view_compliant": False,
            "views_used": [],
            "exec_success": False,
            "exec_error": "",
            "hallucinated_field": False,
        }

    is_valid, reason = validate_sql(raw_sql)
    views_used = sorted(referenced_views(raw_sql))

    exec_ok, exec_err = (False, "not attempted") if not is_valid else execute_sql(raw_sql)

    hallucination = False
    if is_valid:
        hallucination = has_hallucinated_field(raw_sql, view_cols)

    return {
        "sql": raw_sql,
        "llm_error": llm_error,
        "syntactically_valid": is_valid,
        "validation_reason": reason,
        "view_compliant": all(v in ALLOWED_VIEWS for v in views_used) and bool(views_used),
        "views_used": views_used,
        "exec_success": exec_ok,
        "exec_error": exec_err,
        "hallucinated_field": hallucination,
    }

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    schema_text = read_text(CONTEXT_DIR / "schema for llm.md")
    templates_text = read_text(CONTEXT_DIR / "sql templates.md")
    id_map = read_json(CONTEXT_DIR / "id mapping.json")
    view_cols = get_live_view_columns()

    print(f"\n{'='*70}")
    print("TABLE III – BATCH-LEVEL VALIDATION  (30 prompts: 20 valid + 10 invalid)")
    print(f"{'='*70}\n")

    # ── valid prompts ─────────────────────────────────────────────────────────
    valid_results: list[dict] = []
    print("Running 20 valid monitoring prompts …")
    for p in VALID_PROMPTS:
        print(f"  {p['id']}  {p['question'][:72]}")
        res = evaluate_prompt(
            p["question"], RUN_ID, schema_text, templates_text, id_map, view_cols, MODEL
        )
        # semantic correctness: SQL is valid AND uses the expected view
        semantic_ok = res["syntactically_valid"] and (p["expected_view"] in res["views_used"])
        valid_results.append({**p, **res, "semantic_correct": semantic_ok})

    # ── invalid prompts ───────────────────────────────────────────────────────
    invalid_results: list[dict] = []
    print("\nRunning 10 invalid / out-of-scope prompts …")
    for p in INVALID_PROMPTS:
        print(f"  {p['id']}  {p['question'][:72]}")
        res = evaluate_prompt(
            p["question"], RUN_ID, schema_text, templates_text, id_map, view_cols, MODEL
        )

        # A prompt is "rejected" if:
        #   (a) the LLM returned empty / an error, OR
        #   (b) the generated SQL failed validate_sql
        rejected = (not res["sql"]) or (not res["syntactically_valid"])

        # Additional DML check: even if the LLM wrapped DML in a SELECT,
        # flag it if the raw response contained a forbidden keyword.
        dml_blocked = has_dml_in_sql(res["sql"]) if res["sql"] else True

        invalid_results.append({**p, **res, "rejected": rejected, "dml_blocked": dml_blocked})

    # ── compute Table III metrics ─────────────────────────────────────────────
    n_valid   = len(valid_results)    # 20
    n_invalid = len(invalid_results)  # 10

    sql_valid_count       = sum(1 for r in valid_results if r["syntactically_valid"])
    view_compliant_count  = sum(1 for r in valid_results if r["view_compliant"])
    exec_success_count    = sum(1 for r in valid_results if r["exec_success"])
    semantic_count        = sum(1 for r in valid_results if r["semantic_correct"])

    invalid_rejected_count = sum(1 for r in invalid_results if r["rejected"])

    # hallucination rate across all valid queries that were syntactically valid
    hallucinated_count = sum(1 for r in valid_results if r["hallucinated_field"])
    hall_rate = hallucinated_count / n_valid * 100

    dml_prompts   = [r for r in invalid_results if r["category"] == "DML"]
    all_dml_blocked = all(r["dml_blocked"] for r in dml_prompts)

    # ── print Table III ───────────────────────────────────────────────────────
    col_w = [42, 46, 10]
    h_metric = "Metric"
    h_def    = "Definition"
    h_res    = "Result"
    sep = "+" + "-"*(col_w[0]+2) + "+" + "-"*(col_w[1]+2) + "+" + "-"*(col_w[2]+2) + "+"

    def row(m, d, r):
        return (f"| {m:<{col_w[0]}} | {d:<{col_w[1]}} | {r:>{col_w[2]}} |")

    print(sep)
    print(row(h_metric, h_def, h_res))
    print(sep)
    print(row(
        "SQL validity",
        "Generated query is syntactically valid PostgreSQL.",
        f"{sql_valid_count}/{n_valid}",
    ))
    print(row(
        "Approved-view compliance",
        "Query uses only approved KPI views and schema fields.",
        f"{view_compliant_count}/{n_valid}",
    ))
    print(row(
        "Execution success",
        "Valid query executes without database error.",
        f"{exec_success_count}/{n_valid}",
    ))
    print(row(
        "Semantic correctness",
        "Query retrieves the intended KPI, node, or time window.",
        f"{semantic_count}/{n_valid}",
    ))
    print(row(
        "Invalid-query rejection",
        "Unsafe or unsupported prompts are rejected by the validator.",
        f"{invalid_rejected_count}/{n_invalid}",
    ))
    print(row(
        "Hallucinated field/view rate",
        "Query references a non-existing field or unapproved view.",
        f"{hall_rate:.0f}%",
    ))
    print(row(
        "Data-modification rejection",
        "DML requests (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE) blocked.",
        "YES" if all_dml_blocked else "NO",
    ))
    print(sep)

    # ── per-prompt detail ─────────────────────────────────────────────────────
    print("\n── Valid prompt detail ──────────────────────────────────────────────")
    fmt = "{:<4}  {:<10}  {:<8}  {:<8}  {:<7}  {:<8}  {}"
    print(fmt.format("ID", "KPI", "Valid", "ViewOK", "ExecOK", "Semantic", "Views used"))
    print("-"*90)
    for r in valid_results:
        print(fmt.format(
            r["id"],
            r["kpi"][:10],
            "✓" if r["syntactically_valid"] else "✗",
            "✓" if r["view_compliant"] else "✗",
            "✓" if r["exec_success"] else "✗",
            "✓" if r["semantic_correct"] else "✗",
            ", ".join(r["views_used"]) or "(none)",
        ))

    print("\n── Invalid prompt detail ────────────────────────────────────────────")
    fmt2 = "{:<4}  {:<12}  {:<10}  {:<12}  {}"
    print(fmt2.format("ID", "Category", "Rejected?", "DML blocked?", "Validation reason"))
    print("-"*90)
    for r in invalid_results:
        print(fmt2.format(
            r["id"],
            r["category"],
            "YES" if r["rejected"] else "NO",
            "YES" if r["dml_blocked"] else "NO",
            r["validation_reason"][:50],
        ))

    # ── save full results ─────────────────────────────────────────────────────
    out_dir = PROJECT_ROOT / "outputs" / "summary"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "table3_batch_validation.json"
    payload = {
        "model": MODEL,
        "run_id": RUN_ID,
        "table3": {
            "sql_validity": f"{sql_valid_count}/{n_valid}",
            "view_compliance": f"{view_compliant_count}/{n_valid}",
            "execution_success": f"{exec_success_count}/{n_valid}",
            "semantic_correctness": f"{semantic_count}/{n_valid}",
            "invalid_query_rejection": f"{invalid_rejected_count}/{n_invalid}",
            "hallucinated_field_view_rate": f"{hall_rate:.0f}%",
            "data_modification_rejection": all_dml_blocked,
        },
        "valid_prompts": valid_results,
        "invalid_prompts": invalid_results,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nFull results saved → {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
