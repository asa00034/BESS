import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

try:
    from sqlalchemy import create_engine, text
except Exception:
    create_engine = None
    text = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


ALLOWED_VIEWS = {
    "v_voltage_violations",
    "v_soc_summary",
    "v_dr_power_summary",
    "v_voltage_control_summary",
    "v_kpi_run_summary",
}

FORBIDDEN_SQL = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
}

CASE_STUDY_QUESTIONS = [
    "For this run, which nodes have the highest voltage violations?",
    "For this run, summarize SOC by node and highlight the lowest SOC nodes.",
    "For this run, summarize active-power tracking error and rank nodes by max absolute error.",
]

VIEW_DEFAULT_COLUMNS = {
    "v_voltage_violations": ["ts", "node_id", "phase", "voltage_pu", "violation_type", "deviation_pu"],
    "v_soc_summary": ["node_id", "soc_min", "soc_mean", "soc_max", "sample_count", "active_count"],
    "v_dr_power_summary": ["ts", "node_id", "p_ref", "p_meas", "tracking_error", "abs_error"],
    "v_voltage_control_summary": [
        "ts",
        "node_id",
        "q_meas_a",
        "q_meas_b",
        "q_meas_c",
        "q_ref_a",
        "q_ref_b",
        "q_ref_c",
        "v_a",
        "v_b",
        "v_c",
        "q_violation",
        "v_violation",
    ],
    "v_kpi_run_summary": [
        "ts_start",
        "ts_end",
        "total_samples",
        "v_violation_count",
        "v_min",
        "v_max",
        "q_violation_count",
        "fes_mean",
        "mean_abs_dr_error",
        "solve_time_mean_ms",
        "solve_time_max_ms",
        "switch_flag_count",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SQL from NL question in manual validation mode.")
    parser.add_argument("--question", type=str, help="Natural language question")
    parser.add_argument("--run-id", required=True, type=str, help="Run identifier")
    parser.add_argument("--node-id", type=int, help="Optional node identifier")
    parser.add_argument("--model", default="gpt-5.2", help="LLM model for SQL generation")
    parser.add_argument(
        "--context-dir",
        default="agentic_ai/M2",
        help="Directory containing schema for llm.md, sql templates.md, id mapping.json",
    )
    parser.add_argument(
        "--out-dir",
        default="logs/sql drafts",
        help="Output directory for generated SQL drafts",
    )
    parser.add_argument(
        "--case-study",
        action="store_true",
        help="Generate SQL for three built-in case study questions",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    sql = match.group(1).strip() if match else text.strip()
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def referenced_views(sql: str) -> set[str]:
    candidates = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    return {name.lower() for name in candidates}


def validate_sql(sql: str) -> tuple[bool, str]:
    compact = " ".join(sql.split())
    low = compact.lower()

    if not low.startswith("select ") and not low.startswith("with "):
        return False, "SQL must be a single SELECT query."

    if ";" in sql:
        return False, "Multiple statements are not allowed."

    for token in FORBIDDEN_SQL:
        if re.search(rf"\b{token}\b", low):
            return False, f"Forbidden SQL keyword detected: {token}"

    views = referenced_views(sql)
    if not views:
        return False, "No view reference found in SQL."

    disallowed = [view for view in views if view not in ALLOWED_VIEWS]
    if disallowed:
        return False, f"Disallowed source(s): {', '.join(disallowed)}"

    return True, "ok"


def get_live_view_columns() -> dict[str, list[str]]:
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")
    if create_engine is None or text is None:
        return VIEW_DEFAULT_COLUMNS

    try:
        engine = create_engine(db_url, connect_args={"connect_timeout": 5})
        query = text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN (
                'v_voltage_violations',
                'v_soc_summary',
                'v_dr_power_summary',
                'v_voltage_control_summary',
                'v_kpi_run_summary'
              )
            ORDER BY table_name, ordinal_position
            """
        )
        out: dict[str, list[str]] = {view: [] for view in VIEW_DEFAULT_COLUMNS}
        with engine.connect() as conn:
            rows = conn.execute(query).all()
        for table_name, column_name in rows:
            out.setdefault(table_name, []).append(column_name)
        for view_name, default_columns in VIEW_DEFAULT_COLUMNS.items():
            if not out.get(view_name):
                out[view_name] = default_columns
        return out
    except Exception:
        return VIEW_DEFAULT_COLUMNS


def has_column(view_columns: dict[str, list[str]], view_name: str, column_name: str) -> bool:
    return column_name in view_columns.get(view_name, [])


def heuristic_sql(question: str, run_id: str, node_id: int | None, view_columns: dict[str, list[str]]) -> str:
    q = question.lower()
    run_filter_voltage = f"\n  AND run_id = '{run_id}'" if has_column(view_columns, "v_voltage_violations", "run_id") else ""
    run_filter_soc = f"\n  AND run_id = '{run_id}'" if has_column(view_columns, "v_soc_summary", "run_id") else ""
    run_filter_dr = f"\n  AND run_id = '{run_id}'" if has_column(view_columns, "v_dr_power_summary", "run_id") else ""
    run_filter_vctrl = (
        f"\n  AND run_id = '{run_id}'" if has_column(view_columns, "v_voltage_control_summary", "run_id") else ""
    )
    run_filter_kpi = f"\nWHERE run_id = '{run_id}'" if has_column(view_columns, "v_kpi_run_summary", "run_id") else ""

    node_filter_voltage = f"\n  AND node_id = {node_id}" if node_id is not None and has_column(view_columns, "v_voltage_violations", "node_id") else ""
    node_filter_soc = f"\n  AND node_id = {node_id}" if node_id is not None and has_column(view_columns, "v_soc_summary", "node_id") else ""
    node_filter_dr = f"\n  AND node_id = {node_id}" if node_id is not None and has_column(view_columns, "v_dr_power_summary", "node_id") else ""
    node_filter_vctrl = (
        f"\n  AND node_id = {node_id}" if node_id is not None and has_column(view_columns, "v_voltage_control_summary", "node_id") else ""
    )

    if "soc" in q:
        return (
            "SELECT node_id, soc_min, soc_mean, soc_max, sample_count, active_count\n"
            "FROM v_soc_summary\n"
            "WHERE 1=1"
            f"{run_filter_soc}"
            f"{node_filter_soc}\n"
            "ORDER BY soc_mean ASC, node_id"
        )

    if "tracking" in q or "error" in q or "pref" in q or "pmeas" in q:
        return (
            "SELECT ts, node_id, p_ref, p_meas, tracking_error, abs_error\n"
            "FROM v_dr_power_summary\n"
            "WHERE 1=1"
            f"{run_filter_dr}"
            f"{node_filter_dr}\n"
            "ORDER BY abs_error DESC, ts, node_id"
        )

    if "reactive" in q or "qref" in q or "qmeas" in q or "voltage control" in q:
        return (
            "SELECT ts, node_id, q_meas_a, q_meas_b, q_meas_c, q_ref_a, q_ref_b, q_ref_c, v_a, v_b, v_c, q_violation, v_violation\n"
            "FROM v_voltage_control_summary\n"
            "WHERE 1=1"
            f"{run_filter_vctrl}"
            f"{node_filter_vctrl}\n"
            "ORDER BY ts DESC, node_id"
        )

    if "voltage" in q or "violation" in q:
        return (
            "SELECT ts, node_id, phase, voltage_pu, violation_type, deviation_pu\n"
            "FROM v_voltage_violations\n"
            "WHERE 1=1"
            f"{run_filter_voltage}"
            f"{node_filter_voltage}\n"
            "ORDER BY deviation_pu DESC, ts"
        )

    return (
        "SELECT ts_start, ts_end, total_samples, v_violation_count, q_violation_count, v_min, v_max, mean_abs_dr_error\n"
        "FROM v_kpi_run_summary\n"
        f"{run_filter_kpi}\n"
        "ORDER BY ts_start DESC"
    )


def generate_with_llm(prompt: str, model: str) -> str:
    if OpenAI is None:
        raise RuntimeError("openai package is not available")
    client = OpenAI()
    response = client.responses.create(model=model, input=prompt)
    text = getattr(response, "output_text", "")
    if not text:
        text = str(response)
    return extract_sql(text)


def make_prompt(
    question: str,
    run_id: str,
    node_id: int | None,
    schema_text: str,
    templates_text: str,
    id_map: dict,
    view_columns: dict[str, list[str]],
) -> str:
    node_context = f"Node filter: {node_id}" if node_id is not None else "Node filter: none"
    run_view_support = {view: ("run_id" in columns) for view, columns in view_columns.items()}
    return f"""
You are generating PostgreSQL SQL in MANUAL VALIDATION MODE.

Objective:
- Return exactly one SQL query string.
- The query must answer the user question.

Hard constraints:
1) Use ONLY these views: {', '.join(sorted(ALLOWED_VIEWS))}
2) Do not use base tables.
3) Output SQL only (no explanation, no markdown fences).
4) Use run_id = '{run_id}' only for views that contain a run_id column.
5) If node filter is provided, include node_id = {node_id}.

Schema reference:
{schema_text}

SQL template reference:
{templates_text}

Identifier mapping:
{json.dumps(id_map, indent=2)}

Detected view columns:
{json.dumps(view_columns, indent=2)}

Run-id availability by view:
{json.dumps(run_view_support, indent=2)}

Question:
{question}

Run filter: {run_id}
{node_context}
""".strip()


def safe_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned[:80] if cleaned else "query"


def save_sql(out_dir: Path, question: str, sql: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{timestamp}_{safe_slug(question)}.sql"
    file_path = out_dir / name
    file_path.write_text(sql.strip() + "\n", encoding="utf-8")
    return file_path


def save_prompt_log(out_dir: Path, question: str, prompt: str, sql: str, model: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "prompt_sql_log.jsonl"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "question": question,
        "prompt": prompt,
        "sql": sql,
    }
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def generate_one(question: str, run_id: str, node_id: int | None, model: str, context_dir: Path, out_dir: Path) -> Path:
    schema_text = read_text(context_dir / "schema for llm.md")
    templates_text = read_text(context_dir / "sql templates.md")
    id_map = read_json(context_dir / "id mapping.json")
    view_columns = get_live_view_columns()
    prompt = make_prompt(question, run_id, node_id, schema_text, templates_text, id_map, view_columns)

    sql = ""
    llm_error = None
    try:
        sql = generate_with_llm(prompt, model)
    except Exception as error:
        llm_error = str(error)

    if not sql:
        sql = heuristic_sql(question, run_id, node_id, view_columns)

    is_valid, reason = validate_sql(sql)
    if not is_valid:
        sql = heuristic_sql(question, run_id, node_id, view_columns)
        is_valid, reason = validate_sql(sql)
        if not is_valid:
            raise ValueError(f"Unable to produce valid SQL. Reason: {reason}")

    path = save_sql(out_dir, question, sql)
    save_prompt_log(out_dir, question, prompt, sql, model)

    if llm_error:
        print(f"[warn] LLM generation failed; used heuristic SQL. details={llm_error}")
    print(f"Saved SQL draft: {path}")
    return path


def main() -> None:
    load_dotenv()
    args = parse_args()

    context_dir = Path(args.context_dir)
    out_dir = Path(args.out_dir)

    if args.case_study:
        for question in CASE_STUDY_QUESTIONS:
            generate_one(
                question=question,
                run_id=args.run_id,
                node_id=args.node_id,
                model=args.model,
                context_dir=context_dir,
                out_dir=out_dir,
            )
        return

    if not args.question:
        raise ValueError("Provide --question or use --case-study")

    generate_one(
        question=args.question,
        run_id=args.run_id,
        node_id=args.node_id,
        model=args.model,
        context_dir=context_dir,
        out_dir=out_dir,
    )


if __name__ == "__main__":
    main()
