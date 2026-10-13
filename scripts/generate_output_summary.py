import argparse
import json
import re
from datetime import datetime
from html import escape
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HTML summary for LLM pipeline outputs.")
    parser.add_argument("--final-dir", default="outputs/final answers", help="Directory with final answer JSON files")
    parser.add_argument("--sql-dir", default="outputs/sql results", help="Directory with SQL result JSON files")
    parser.add_argument(
        "--constraint-dir",
        default="outputs/constraint checks",
        help="Directory with constraint decision JSON files",
    )
    parser.add_argument("--out-dir", default="outputs/summary", help="Directory for generated summary HTML")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def label_class(label: str) -> str:
    normalized = (label or "unknown").lower()
    if normalized in {"stable", "vulnerable", "unstable", "constrained"}:
        return normalized
    return "unknown"


def clean_answer_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("\\(", "")
    cleaned = cleaned.replace("\\)", "")
    cleaned = cleaned.replace("\\[", "")
    cleaned = cleaned.replace("\\]", "")
    cleaned = cleaned.replace("\\_", "_")
    cleaned = re.sub(r"\\text\{([^}]*)\}", r"\1", cleaned)
    cleaned = cleaned.replace("\\approx", "~")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def dict_to_rows(data: dict) -> str:
    rows = []
    for key, value in data.items():
        rows.append(f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>")
    return "\n".join(rows)


def preview_table(rows: list[dict], max_rows: int = 3) -> str:
    if not rows:
        return "<p>No preview rows available.</p>"

    shown = rows[:max_rows]
    cols = list(shown[0].keys())
    thead = "".join(f"<th>{escape(str(col))}</th>" for col in cols)
    body = []
    for row in shown:
        body.append("<tr>" + "".join(f"<td>{escape(str(row.get(col, '')))}</td>" for col in cols) + "</tr>")
    return (
        "<table class='preview'><thead><tr>"
        + thead
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def build_card(final_payload: dict, sql_payload: dict, constraint_payload: dict) -> str:
    qid = final_payload.get("question_id", "unknown")
    question = final_payload.get("question", "")
    label = (
        final_payload.get("constraint_label")
        or constraint_payload.get("decision", {}).get("label")
        or "unknown"
    )
    row_count = sql_payload.get("row_count", final_payload.get("row_count", 0))
    exec_ms = sql_payload.get("execution_time_ms", "n/a")
    sql_text = final_payload.get("sql", sql_payload.get("sql", ""))
    answer = clean_answer_text(final_payload.get("final_answer", ""))
    metrics = constraint_payload.get("decision", {}).get("metrics", {})
    preview = sql_payload.get("rows", final_payload.get("result_snippet", []))

    selected_metric_keys = [
        "voltage_violation_duration",
        "max_deviation_pu",
        "soc_min",
        "soc_max",
        "max_abs_tracking_error",
    ]
    key_metrics = {key: metrics.get(key) for key in selected_metric_keys if key in metrics}
    if not key_metrics:
        key_metrics = metrics

    sql_file = final_payload.get("sql_file", "n/a")
    compact_answer = answer

    return f"""
<section>
    <h3>{escape(qid)} - {escape(label)}</h3>
    <p><strong>Question:</strong> {escape(question)}</p>
    <p><strong>Rows:</strong> {escape(str(row_count))} | <strong>Execution ms:</strong> {escape(str(exec_ms))}</p>
    <p><strong>SQL file:</strong> {escape(str(sql_file))}</p>
    <p><strong>Answer:</strong> {escape(compact_answer)}</p>

    <details>
        <summary>Details</summary>
        <h4>Key metrics</h4>
        <table>{dict_to_rows(key_metrics)}</table>
        <h4>SQL</h4>
        <pre>{escape(sql_text)}</pre>
        <h4>Result preview</h4>
        {preview_table(preview, max_rows=3)}
    </details>
</section>
<hr />
"""


def main() -> None:
    args = parse_args()
    final_dir = Path(args.final_dir)
    sql_dir = Path(args.sql_dir)
    constraint_dir = Path(args.constraint_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    final_files = sorted(final_dir.glob("*.json"))
    cards = []
    labels: dict[str, int] = {"stable": 0, "vulnerable": 0, "unstable": 0, "constrained": 0, "unknown": 0}

    for final_file in final_files:
        final_payload = read_json(final_file)
        qid = final_payload.get("question_id") or final_file.stem

        sql_path = sql_dir / f"{qid}.json"
        constraint_path = constraint_dir / f"{qid}.decision.json"

        sql_payload = read_json(sql_path) if sql_path.exists() else {}
        constraint_payload = read_json(constraint_path) if constraint_path.exists() else {}

        label = (
            final_payload.get("constraint_label")
            or constraint_payload.get("decision", {}).get("label")
            or "unknown"
        )
        labels[label_class(label)] = labels.get(label_class(label), 0) + 1

        cards.append(build_card(final_payload, sql_payload, constraint_payload))

    generated_at = datetime.now().isoformat(timespec="seconds")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LLM Output Summary</title>
  <style>
        body {{ font-family: Arial, sans-serif; margin: 16px; line-height: 1.4; }}
        h1 {{ margin-top: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; vertical-align: top; }}
        pre {{ background: #f4f4f4; padding: 8px; overflow-x: auto; }}
        summary {{ cursor: pointer; }}
        hr {{ margin: 16px 0; }}
  </style>
</head>
<body>
    <h1>LLM Output Summary</h1>
    <p>Generated at: {escape(generated_at)}</p>
    <table>
        <tr><th>Total Questions</th><th>Stable</th><th>Vulnerable</th><th>Unstable</th><th>Constrained</th><th>Unknown</th></tr>
        <tr>
            <td>{len(final_files)}</td>
            <td>{labels.get('stable', 0)}</td>
            <td>{labels.get('vulnerable', 0)}</td>
            <td>{labels.get('unstable', 0)}</td>
            <td>{labels.get('constrained', 0)}</td>
            <td>{labels.get('unknown', 0)}</td>
        </tr>
    </table>
    {''.join(cards) if cards else '<p>No final answer files found.</p>'}
</body>
</html>
"""

    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"Summary generated: {out_file}")


if __name__ == "__main__":
    main()
