import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


CASE_STUDY_QUESTIONS = [
    "For this run, which nodes have the highest voltage violations?",
    "For this run, summarize SOC by node and highlight the lowest SOC nodes.",
    "For this run, summarize active-power tracking error and rank nodes by max absolute error.",
]

DEFAULT_QUESTIONS_FILE = "agentic_ai/M2/test_questions_v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated end-to-end SQL answering pipeline.")
    parser.add_argument("--question", type=str, help="Question text")
    parser.add_argument("--run-id", required=True, type=str, help="Run id")
    parser.add_argument("--node-id", type=int, help="Optional node id")
    parser.add_argument("--model", default="gpt-5.2", help="LLM model")
    parser.add_argument("--case-study", action="store_true", help="Run the 3 default case-study questions")
    parser.add_argument(
        "--questions-file",
        default=DEFAULT_QUESTIONS_FILE,
        help="JSON file containing case-study questions with optional ids",
    )
    parser.add_argument("--question-id", type=str, default="query", help="Identifier for outputs")
    parser.add_argument("--out-dir", type=str, default="outputs/final answers", help="Final answer output directory")
    return parser.parse_args()


def safe_name(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "query"


def load_case_study_questions(questions_file: str) -> list[tuple[str, str]]:
    path = Path(questions_file)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded: list[tuple[str, str]] = []
        if isinstance(data, list):
            for index, item in enumerate(data, start=1):
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                if not question:
                    continue
                qid = str(item.get("id", f"case_study_q{index}")).strip() or f"case_study_q{index}"
                loaded.append((safe_name(qid), question))
        if loaded:
            return loaded

    # Fallback to built-in questions when the file is missing or empty.
    return [(f"case_study_q{i}", q) for i, q in enumerate(CASE_STUDY_QUESTIONS, start=1)]


def run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True)


def sanitize_answer_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    # Remove code fences and markdown emphasis markers.
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("`", "")

    # Convert common LaTeX wrappers to plain text.
    cleaned = cleaned.replace("\\(", "")
    cleaned = cleaned.replace("\\)", "")
    cleaned = cleaned.replace("\\[", "")
    cleaned = cleaned.replace("\\]", "")
    cleaned = cleaned.replace("\\_", "_")
    cleaned = re.sub(r"\\text\{([^}]*)\}", r"\1", cleaned)
    cleaned = cleaned.replace("\\approx", "~")

    # Normalize repeated whitespace.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_saved_sql_path(stdout_text: str) -> Path | None:
    marker = "Saved SQL draft: "
    for line in stdout_text.splitlines()[::-1]:
        if marker in line:
            return Path(line.split(marker, 1)[1].strip())
    return None


def call_sql_generator(question: str, run_id: str, node_id: int | None, model: str) -> tuple[Path, str]:
    py = sys.executable
    command = [
        py,
        "llm generate sql.py",
        "--question",
        question,
        "--run-id",
        run_id,
        "--model",
        model,
    ]
    if node_id is not None:
        command.extend(["--node-id", str(node_id)])

    result = run_command(command)
    if result.returncode != 0:
        raise RuntimeError(f"SQL generation failed: {result.stderr or result.stdout}")

    sql_path = parse_saved_sql_path(result.stdout)
    if not sql_path:
        raise RuntimeError(f"Could not parse SQL output path from generator stdout: {result.stdout}")

    sql_text = sql_path.read_text(encoding="utf-8")
    return sql_path, sql_text


def call_sql_runner(question_id: str, sql_path: Path) -> dict:
    py = sys.executable
    command = [
        py,
        "run sql.py",
        "--sql-file",
        str(sql_path),
        "--question-id",
        question_id,
        "--format",
        "json",
        "--out-dir",
        "outputs/sql results",
    ]
    result = run_command(command)
    if result.returncode != 0:
        raise RuntimeError(f"SQL execution command failed: {result.stderr or result.stdout}")

    metadata = json.loads(result.stdout)
    if metadata.get("output_json"):
        payload_path = Path(metadata["output_json"])
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "question_id": question_id,
            "status": metadata.get("status", "failed"),
            "row_count": metadata.get("row_count", 0),
            "columns": metadata.get("columns", []),
            "execution_time_ms": metadata.get("execution_time_ms", None),
            "rows": [],
            "sql": sql_path.read_text(encoding="utf-8"),
        }

    return {"metadata": metadata, "payload": payload}


def call_constraint_check(question_id: str, result_json_path: Path) -> dict:
    py = sys.executable
    command = [
        py,
        "constraint check.py",
        "--input",
        str(result_json_path),
        "--question-id",
        question_id,
        "--constraints",
        "agentic_ai/M2/operational constraints.md",
        "--out-dir",
        "outputs/constraint checks",
    ]
    result = run_command(command)
    if result.returncode != 0:
        raise RuntimeError(f"Constraint check failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def generate_final_answer(question: str, sql_payload: dict, constraint_summary: dict, model: str) -> str:
    rows = sql_payload.get("rows", [])
    preview = rows[:5]
    label = constraint_summary.get("decision", {}).get("label", "unknown")
    metrics = constraint_summary.get("decision", {}).get("metrics", {})

    if OpenAI is None or os.getenv("OPENAI_API_KEY") is None:
        fallback = (
            f"Condition label: {label}. Returned {sql_payload.get('row_count', 0)} rows in "
            f"{sql_payload.get('execution_time_ms', 'n/a')} ms. Key metrics: {metrics}."
        )
        return sanitize_answer_text(fallback)

    prompt = f"""
You are an engineering analyst.

Question: {question}

SQL used:
{sql_payload.get('sql', '')}

Result columns: {sql_payload.get('columns', [])}
Result row count: {sql_payload.get('row_count', 0)}
Result preview (first up to 5 rows):
{json.dumps(preview, indent=2)}

Constraint decision:
{json.dumps(constraint_summary, indent=2)}

Write a concise technical answer in 4-7 sentences:
- directly answer the question,
- reference one or two concrete values,
- state the condition label ({label}),
- include one recommendation.
Formatting rules:
- plain text only
- no markdown
- no LaTeX math wrappers like \( ... \)
- no escape sequences like \\_ or \\text{{...}}
""".strip()

    client = OpenAI()
    response = client.responses.create(model=model, input=prompt)
    text = getattr(response, "output_text", None)
    if text:
        return sanitize_answer_text(str(text))
    return sanitize_answer_text(str(response))


def build_refinement_prompt(question: str, prior_sql: str, error_text: str) -> str:
    return f"""
Refine this SQL once.

Question:
{question}

Previous SQL:
{prior_sql}

Execution issue:
{error_text}

Return only a corrected single PostgreSQL SELECT query using allowed KPI views.
""".strip()


def append_refinement_log(entry: dict, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict]
    if log_path.exists():
        existing = json.loads(log_path.read_text(encoding="utf-8"))
    else:
        existing = []
    existing.append(entry)
    log_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def write_final_record(question_id: str, out_dir: Path, record: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{question_id}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def execute_pipeline_once(
    question: str,
    run_id: str,
    node_id: int | None,
    question_id: str,
    model: str,
    out_dir: Path,
) -> Path:
    attempt_1_path, attempt_1_sql = call_sql_generator(question, run_id, node_id, model)
    run_1 = call_sql_runner(question_id, attempt_1_path)

    need_retry = run_1["metadata"].get("status") != "success" or int(run_1["metadata"].get("row_count", 0)) == 0

    refinement_log_path = Path("logs/refinement.json")
    final_sql_path = attempt_1_path
    final_sql = attempt_1_sql
    final_run = run_1

    if need_retry:
        issue = run_1["metadata"].get("error") or "empty result set"
        refinement_prompt = build_refinement_prompt(question, attempt_1_sql, issue)

        if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
            client = OpenAI()
            response = client.responses.create(model=model, input=refinement_prompt)
            refined_sql = getattr(response, "output_text", None) or str(response)
        else:
            refined_sql = attempt_1_sql

        refined_path = Path("logs/sql drafts") / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{question_id}_refined.sql"
        refined_path.parent.mkdir(parents=True, exist_ok=True)
        refined_path.write_text(refined_sql.strip() + "\n", encoding="utf-8")

        run_2 = call_sql_runner(question_id, refined_path)

        append_refinement_log(
            {
                "timestamp": datetime.now().isoformat(),
                "question_id": question_id,
                "question": question,
                "attempt_1_sql_file": str(attempt_1_path).replace("\\", "/"),
                "attempt_1_status": run_1["metadata"].get("status"),
                "attempt_1_row_count": run_1["metadata"].get("row_count"),
                "attempt_1_error": run_1["metadata"].get("error"),
                "refinement_prompt": refinement_prompt,
                "attempt_2_sql_file": str(refined_path).replace("\\", "/"),
                "attempt_2_status": run_2["metadata"].get("status"),
                "attempt_2_row_count": run_2["metadata"].get("row_count"),
                "attempt_2_error": run_2["metadata"].get("error"),
            },
            refinement_log_path,
        )

        final_sql_path = refined_path
        final_sql = refined_sql
        final_run = run_2

    result_json_path = Path("outputs/sql results") / f"{question_id}.json"
    if result_json_path.exists():
        constraint_summary = call_constraint_check(question_id, result_json_path)
    else:
        fallback_payload = {
            "question_id": question_id,
            "status": final_run["metadata"].get("status", "failed"),
            "row_count": final_run["metadata"].get("row_count", 0),
            "columns": final_run["metadata"].get("columns", []),
            "execution_time_ms": final_run["metadata"].get("execution_time_ms", None),
            "sql": final_sql,
            "rows": [],
        }
        result_json_path.parent.mkdir(parents=True, exist_ok=True)
        result_json_path.write_text(json.dumps(fallback_payload, indent=2), encoding="utf-8")
        constraint_summary = call_constraint_check(question_id, result_json_path)

    sql_payload = json.loads(result_json_path.read_text(encoding="utf-8"))
    final_text = generate_final_answer(question, sql_payload, constraint_summary, model)

    record = {
        "timestamp": datetime.now().isoformat(),
        "question_id": question_id,
        "question": question,
        "run_id": run_id,
        "node_id": node_id,
        "sql_file": str(final_sql_path).replace("\\", "/"),
        "sql": final_sql.strip(),
        "result_snippet": sql_payload.get("rows", [])[:5],
        "result_columns": sql_payload.get("columns", []),
        "row_count": sql_payload.get("row_count", 0),
        "constraint_label": constraint_summary.get("decision", {}).get("label", "unknown"),
        "constraint_summary": constraint_summary,
        "final_answer": final_text,
    }
    return write_final_record(question_id, out_dir, record)


def run_case_study(run_id: str, node_id: int | None, model: str, out_dir: Path, questions_file: str) -> list[Path]:
    outputs: list[Path] = []
    for question_id, question in load_case_study_questions(questions_file):
        output_path = execute_pipeline_once(
            question=question,
            run_id=run_id,
            node_id=node_id,
            question_id=question_id,
            model=model,
            out_dir=out_dir,
        )
        outputs.append(output_path)
    return outputs


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.case_study:
        files = run_case_study(args.run_id, args.node_id, args.model, Path(args.out_dir), args.questions_file)
        print(json.dumps({"outputs": [str(p).replace("\\", "/") for p in files]}, indent=2))
        return

    if not args.question:
        raise ValueError("Provide --question or set --case-study")

    qid = safe_name(args.question_id if args.question_id else args.question)
    result_file = execute_pipeline_once(
        question=args.question,
        run_id=args.run_id,
        node_id=args.node_id,
        question_id=qid,
        model=args.model,
        out_dir=Path(args.out_dir),
    )
    print(json.dumps({"output": str(result_file).replace("\\", "/")}, indent=2))


if __name__ == "__main__":
    main()
