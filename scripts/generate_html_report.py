"""Generate a self-contained HTML report from the pipeline outputs (q1-q4)."""

from __future__ import annotations

import json
import pathlib
import html as html_module
from datetime import datetime

CASE_LABELS = {
    "q1": "Case A – Voltage Stability Duration Assessment",
    "q2": "Case B – Most Voltage-Vulnerable Node Identification",
    "q3": "Case C – Reactive Power Overshoot Detection",
    "q4": "Case D – Demand Response Active-Power Tracking",
}

ANSWERS_DIR = pathlib.Path("outputs/final answers")
OUT_PATH = pathlib.Path("outputs/report.html")


def label_badge(label: str) -> str:
    colors = {
        "stable": ("#1a7a1a", "#d4edda"),
        "vulnerable": ("#7a4f00", "#fff3cd"),
        "unstable": ("#7a1a1a", "#f8d7da"),
    }
    fg, bg = colors.get(label.lower(), ("#333", "#eee"))
    return (
        f'<span class="badge" style="background:{bg};color:{fg};'
        f'border:1px solid {fg}20">{html_module.escape(label.upper())}</span>'
    )


def metric_row(key: str, value: object) -> str:
    if value is None:
        display = '<span class="null">—</span>'
    elif isinstance(value, bool):
        display = '<span class="bool-true">Yes</span>' if value else '<span class="bool-false">No</span>'
    elif isinstance(value, float):
        display = f"{value:.6g}"
    else:
        display = html_module.escape(str(value))
    return f"<tr><td>{html_module.escape(key)}</td><td>{display}</td></tr>"


def snippet_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "<p class='muted'>No result rows.</p>"
    headers = "".join(f"<th>{html_module.escape(c)}</th>" for c in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{html_module.escape(str(row.get(c, '')))}</td>" for c in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        '<div class="table-wrap"><table class="data-table">'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def build_card(data: dict, case_id: str) -> str:
    title = CASE_LABELS.get(case_id, case_id.upper())
    question = html_module.escape(data.get("question", ""))
    run_id = html_module.escape(data.get("run_id", ""))
    timestamp = html_module.escape(data.get("timestamp", ""))
    row_count = data.get("row_count", 0)
    label = data.get("constraint_label", "unknown")
    final_answer = html_module.escape(data.get("final_answer", ""))
    sql_text = html_module.escape(data.get("sql", "").strip())
    columns = data.get("result_columns", [])
    snippet = data.get("result_snippet", [])
    metrics = data.get("constraint_summary", {}).get("decision", {}).get("metrics", {})
    rationale = html_module.escape(
        data.get("constraint_summary", {}).get("decision", {}).get("rationale", "")
    )

    metric_rows_html = "".join(metric_row(k, v) for k, v in metrics.items())

    return f"""
<section class="card" id="{case_id}">
  <div class="card-header">
    <span class="case-id">{html_module.escape(case_id.upper())}</span>
    <h2>{html_module.escape(title)}</h2>
    {label_badge(label)}
  </div>

  <div class="meta-row">
    <span><strong>Run&nbsp;ID:</strong> {run_id}</span>
    <span><strong>Timestamp:</strong> {timestamp}</span>
    <span><strong>Rows&nbsp;returned:</strong> {row_count}</span>
  </div>

  <div class="block">
    <h3>Operator Prompt</h3>
    <blockquote>{question}</blockquote>
  </div>

  <div class="block">
    <h3>Engineering Assessment</h3>
    <p class="answer">{final_answer}</p>
    <p class="rationale"><em>Constraint rationale: {rationale}</em></p>
  </div>

  <div class="block">
    <h3>Result Preview <span class="muted">(first {len(snippet)} of {row_count} rows)</span></h3>
    {snippet_table(snippet, columns)}
  </div>

  <div class="block collapsible">
    <h3 class="toggle" onclick="toggleBlock(this)">&#9654; Constraint Metrics</h3>
    <div class="collapsible-content" style="display:none">
      <table class="metrics-table">
        <thead><tr><th>Metric</th><th>Value</th></tr></thead>
        <tbody>{metric_rows_html}</tbody>
      </table>
    </div>
  </div>

  <div class="block collapsible">
    <h3 class="toggle" onclick="toggleBlock(this)">&#9654; Generated SQL</h3>
    <div class="collapsible-content" style="display:none">
      <pre class="sql-block">{sql_text}</pre>
    </div>
  </div>
</section>
"""


def build_html(cards: list[str], run_id: str, generated_at: str) -> str:
    toc_items = "".join(
        f'<li><a href="#{qid}">{html_module.escape(CASE_LABELS.get(qid, qid))}</a></li>'
        for qid in CASE_LABELS
    )
    body = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grid Copilot – Pipeline Report ({html_module.escape(run_id)})</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #f4f6f9;
    color: #1a1a2e;
    margin: 0;
    padding: 0;
  }}
  header {{
    background: linear-gradient(135deg, #0d1b2a 0%, #1b4f72 100%);
    color: #e8f4fd;
    padding: 2rem 2.5rem 1.5rem;
  }}
  header h1 {{ margin: 0 0 0.3rem; font-size: 1.7rem; font-weight: 700; }}
  header .sub {{ font-size: 0.9rem; opacity: 0.75; }}
  nav {{
    background: #fff;
    border-bottom: 1px solid #dde3ea;
    padding: 0.75rem 2.5rem;
  }}
  nav ol {{
    margin: 0; padding: 0; list-style: none;
    display: flex; gap: 1.5rem; flex-wrap: wrap;
  }}
  nav ol li a {{
    color: #1b4f72; text-decoration: none; font-size: 0.88rem; font-weight: 500;
  }}
  nav ol li a:hover {{ text-decoration: underline; }}
  main {{ max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem 4rem; }}
  .card {{
    background: #fff;
    border: 1px solid #dde3ea;
    border-radius: 10px;
    margin-bottom: 2rem;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  }}
  .card-header {{
    background: #f0f4f9;
    padding: 1.1rem 1.5rem 0.9rem;
    display: flex;
    align-items: center;
    gap: 0.9rem;
    border-bottom: 1px solid #dde3ea;
    flex-wrap: wrap;
  }}
  .case-id {{
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    background: #1b4f72;
    color: #fff;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
  }}
  .card-header h2 {{
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    flex: 1;
  }}
  .badge {{
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.25rem 0.65rem;
    border-radius: 20px;
    white-space: nowrap;
  }}
  .meta-row {{
    padding: 0.55rem 1.5rem;
    background: #fafbfd;
    border-bottom: 1px solid #eef1f5;
    display: flex;
    gap: 2rem;
    font-size: 0.82rem;
    color: #555;
    flex-wrap: wrap;
  }}
  .block {{ padding: 1.1rem 1.5rem; border-bottom: 1px solid #eef1f5; }}
  .block:last-child {{ border-bottom: none; }}
  .block h3 {{
    margin: 0 0 0.7rem;
    font-size: 0.88rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #1b4f72;
  }}
  blockquote {{
    margin: 0;
    padding: 0.7rem 1rem;
    background: #f0f4f9;
    border-left: 3px solid #1b4f72;
    border-radius: 4px;
    font-style: italic;
    font-size: 0.95rem;
    color: #2c3e50;
  }}
  .answer {{
    line-height: 1.7;
    font-size: 0.95rem;
    margin: 0 0 0.5rem;
  }}
  .rationale {{ font-size: 0.83rem; color: #666; margin: 0; }}
  .table-wrap {{ overflow-x: auto; }}
  table.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }}
  table.data-table th {{
    background: #1b4f72;
    color: #fff;
    padding: 0.45rem 0.7rem;
    text-align: left;
    white-space: nowrap;
  }}
  table.data-table td {{
    padding: 0.4rem 0.7rem;
    border-bottom: 1px solid #eef1f5;
  }}
  table.data-table tr:hover td {{ background: #f7fafd; }}
  table.metrics-table {{
    border-collapse: collapse;
    font-size: 0.82rem;
    width: 100%;
    max-width: 480px;
  }}
  table.metrics-table th {{
    background: #e8eef5;
    color: #1a1a2e;
    padding: 0.4rem 0.7rem;
    text-align: left;
  }}
  table.metrics-table td {{ padding: 0.35rem 0.7rem; border-bottom: 1px solid #eef1f5; }}
  .toggle {{
    cursor: pointer;
    user-select: none;
    margin: 0 0 0.5rem;
    font-size: 0.88rem;
    color: #1b4f72;
  }}
  .toggle:hover {{ text-decoration: underline; }}
  pre.sql-block {{
    background: #1a1a2e;
    color: #e8f4fd;
    padding: 1rem;
    border-radius: 6px;
    font-size: 0.82rem;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
    margin: 0;
    line-height: 1.5;
  }}
  .muted {{ color: #999; font-weight: normal; }}
  .null {{ color: #bbb; font-style: italic; }}
  .bool-true {{ color: #1a7a1a; font-weight: 600; }}
  .bool-false {{ color: #999; }}
  footer {{
    text-align: center;
    font-size: 0.78rem;
    color: #999;
    padding: 1.5rem;
  }}
</style>
</head>
<body>
<header>
  <h1>Grid Copilot &mdash; Agentic SQL Pipeline Report</h1>
  <div class="sub">
    Run ID: <strong>{html_module.escape(run_id)}</strong> &nbsp;|&nbsp;
    Generated: <strong>{html_module.escape(generated_at)}</strong>
  </div>
</header>
<nav>
  <ol>{toc_items}</ol>
</nav>
<main>
{body}
</main>
<footer>Generated by scripts/generate_html_report.py</footer>
<script>
function toggleBlock(el) {{
  var content = el.parentElement.querySelector('.collapsible-content');
  if (!content) return;
  var open = content.style.display !== 'none';
  content.style.display = open ? 'none' : 'block';
  el.textContent = (open ? '\u25BA ' : '\u25BC ') + el.textContent.slice(2);
}}
</script>
</body>
</html>
"""


def main() -> None:
    cards = []
    run_id = "unknown"
    for case_id in ["q1", "q2", "q3", "q4"]:
        path = ANSWERS_DIR / f"{case_id}.json"
        if not path.exists():
            print(f"  Skipping {case_id} — file not found.")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        run_id = data.get("run_id", run_id)
        cards.append(build_card(data, case_id))
        print(f"  Loaded {case_id}: {data.get('question', '')[:60]}...")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_content = build_html(cards, run_id, generated_at)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_content, encoding="utf-8")
    print(f"\nReport written to: {OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
