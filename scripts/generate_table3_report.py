#!/usr/bin/env python3
"""Generate outputs/table3_report.html from table3_batch_validation.json."""

import json
import html as _html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "outputs" / "summary" / "table3_batch_validation.json"
OUT_PATH  = ROOT / "outputs" / "table3_report.html"

KPI_LABELS = {
    "voltage_violation": "Voltage Violation",
    "q_overshoot":       "Q Overshoot",
    "dr_tracking":       "DR Tracking",
    "soc_limits":        "SOC Limits",
    "latency":           "Latency",
    "anomaly_flags":     "Anomaly Flags",
    "kpi_summary":       "KPI Summary",
}

KPI_COLORS = {
    "voltage_violation": "#c0392b",
    "q_overshoot":       "#8e44ad",
    "dr_tracking":       "#2980b9",
    "soc_limits":        "#27ae60",
    "latency":           "#e67e22",
    "anomaly_flags":     "#16a085",
    "kpi_summary":       "#2c3e50",
}

def e(s: str) -> str:
    return _html.escape(str(s))

def tick(ok: bool, label: str = "") -> str:
    cls = "pass" if ok else "fail"
    sym = "✓" if ok else "✗"
    return f'<span class="badge-status {cls}">{sym}{" " + label if label else ""}</span>'

def score_bar(num: int, den: int) -> str:
    pct = num / den * 100
    color = "#27ae60" if num == den else ("#e67e22" if pct >= 70 else "#c0392b")
    return (
        f'<div class="score-wrap">'
        f'<div class="score-label">{num}/{den}</div>'
        f'<div class="score-track"><div class="score-fill" style="width:{pct:.1f}%;background:{color}"></div></div>'
        f'</div>'
    )

def render_sql(sql: str, prompt_id: str) -> str:
    return (
        f'<details class="sql-details"><summary>View generated SQL</summary>'
        f'<pre class="sql-block">{e(sql)}</pre></details>'
    )

def valid_card(r: dict) -> str:
    kpi = r.get("kpi", "")
    kpi_label = KPI_LABELS.get(kpi, kpi)
    kpi_color = KPI_COLORS.get(kpi, "#555")
    views = ", ".join(r.get("views_used", [])) or "—"
    hall = r.get("hallucinated_field", False)
    sem = r.get("semantic_correct", False)
    valid = r.get("syntactically_valid", False)
    view_ok = r.get("view_compliant", False)
    exec_ok = r.get("exec_success", False)
    all_pass = valid and view_ok and exec_ok and sem and not hall
    border = "#27ae60" if all_pass else "#e67e22"
    return f"""
<div class="prompt-card" style="border-left:4px solid {border}">
  <div class="prompt-header">
    <span class="pid-badge">{e(r['id'])}</span>
    <span class="kpi-pill" style="background:{kpi_color}">{e(kpi_label)}</span>
    <span class="prompt-q">{e(r['question'])}</span>
  </div>
  <div class="prompt-checks">
    {tick(valid, "SQL Valid")}
    {tick(view_ok, "View OK")}
    {tick(exec_ok, "Exec OK")}
    {tick(sem, "Semantic")}
    {tick(not hall, "No Halluc.")}
  </div>
  <div class="prompt-meta">
    Views used: <code>{e(views)}</code>
    &nbsp;|&nbsp; Expected: <code>{e(r.get('expected_view',''))}</code>
  </div>
  {render_sql(r.get('sql',''), r['id'])}
</div>"""

def invalid_card(r: dict) -> str:
    rejected = r.get("rejected", False)
    dml = r.get("dml_blocked", False)
    cat = r.get("category", "")
    reason = r.get("validation_reason", "")
    border = "#27ae60" if rejected else "#c0392b"
    rej_label = "REJECTED" if rejected else "NOT REJECTED"
    rej_class = "rej-yes" if rejected else "rej-no"
    views = ", ".join(r.get("views_used", [])) or "—"
    return f"""
<div class="prompt-card" style="border-left:4px solid {border}">
  <div class="prompt-header">
    <span class="pid-badge inv">{e(r['id'])}</span>
    <span class="cat-pill">{e(cat)}</span>
    <span class="prompt-q">{e(r['question'])}</span>
  </div>
  <div class="prompt-checks">
    <span class="badge-status {rej_class}">{rej_label}</span>
    {tick(dml, "DML Blocked") if cat == "DML" else ""}
  </div>
  <div class="prompt-meta">
    Validator reason: <em>{e(reason)}</em>
    &nbsp;|&nbsp; Views used: <code>{e(views)}</code>
  </div>
  {render_sql(r.get('sql',''), r['id'])}
</div>"""

def metric_card(title: str, value: str, sub: str, accent: str) -> str:
    return f"""
<div class="metric-card" style="border-top:3px solid {accent}">
  <div class="metric-val">{e(value)}</div>
  <div class="metric-title">{e(title)}</div>
  <div class="metric-sub">{e(sub)}</div>
</div>"""

def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    t3   = data["table3"]
    vps  = data["valid_prompts"]
    ips  = data["invalid_prompts"]

    hall_rate = t3["hallucinated_field_view_rate"]
    dml_ok    = t3["data_modification_rejection"]

    valid_cards   = "\n".join(valid_card(r) for r in vps)
    invalid_cards = "\n".join(invalid_card(r) for r in ips)

    def frac(s: str):
        n, d = map(int, s.split("/"))
        return n, d

    sv_n, sv_d = frac(t3["sql_validity"])
    vc_n, vc_d = frac(t3["view_compliance"])
    es_n, es_d = frac(t3["execution_success"])
    sc_n, sc_d = frac(t3["semantic_correctness"])
    iq_n, iq_d = frac(t3["invalid_query_rejection"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grid Copilot – Table III Batch Validation</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; }}
body {{
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #f4f6f9;
  color: #1a1a2e;
  margin: 0; padding: 0;
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
  padding: 0.7rem 2.5rem;
}}
nav a {{
  color: #1b4f72; text-decoration: none;
  font-size: 0.88rem; font-weight: 500; margin-right: 1.8rem;
}}
nav a:hover {{ text-decoration: underline; }}
main {{ max-width: 1120px; margin: 2rem auto; padding: 0 1.5rem 4rem; }}
h2 {{
  font-size: 1.1rem; font-weight: 700;
  color: #0d1b2a; border-bottom: 2px solid #1b4f72;
  padding-bottom: 0.4rem; margin: 2.5rem 0 1rem;
}}
/* ── metric grid ── */
.metric-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
  gap: 1rem; margin-bottom: 2rem;
}}
.metric-card {{
  background: #fff;
  border: 1px solid #dde3ea;
  border-radius: 8px;
  padding: 1.1rem 1rem 0.9rem;
  box-shadow: 0 2px 6px rgba(0,0,0,0.05);
}}
.metric-val {{
  font-size: 1.9rem; font-weight: 700;
  color: #0d1b2a; line-height: 1.1;
}}
.metric-title {{
  font-size: 0.78rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.07em;
  color: #555; margin: 0.35rem 0 0.2rem;
}}
.metric-sub {{
  font-size: 0.72rem; color: #888; line-height: 1.3;
}}
/* ── score bar ── */
.score-wrap {{ display: flex; align-items: center; gap: 0.5rem; margin-top: 0.4rem; }}
.score-label {{ font-size: 0.78rem; font-weight: 700; min-width: 36px; color: #0d1b2a; }}
.score-track {{
  flex: 1; background: #e8eef5; border-radius: 4px; height: 6px;
}}
.score-fill {{ height: 6px; border-radius: 4px; transition: width 0.3s; }}
/* ── table III ── */
.t3-wrap {{ overflow-x: auto; margin-bottom: 2rem; }}
table.t3 {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
table.t3 th {{
  background: #1b4f72; color: #fff;
  padding: 0.55rem 1rem; text-align: left;
}}
table.t3 td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #eef1f5; vertical-align: middle; }}
table.t3 tr:hover td {{ background: #f7fafd; }}
table.t3 .result-cell {{ font-weight: 700; white-space: nowrap; }}
/* ── prompt cards ── */
.prompt-card {{
  background: #fff;
  border: 1px solid #dde3ea;
  border-radius: 8px;
  padding: 1rem 1.2rem;
  margin-bottom: 1rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}
.prompt-header {{
  display: flex; align-items: flex-start;
  gap: 0.6rem; margin-bottom: 0.5rem; flex-wrap: wrap;
}}
.pid-badge {{
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
  background: #1b4f72; color: #fff;
  padding: 0.2rem 0.55rem; border-radius: 4px; white-space: nowrap;
  margin-top: 0.1rem;
}}
.pid-badge.inv {{ background: #6c3483; }}
.kpi-pill {{
  font-size: 0.72rem; font-weight: 700; color: #fff;
  padding: 0.2rem 0.55rem; border-radius: 12px; white-space: nowrap;
  margin-top: 0.1rem;
}}
.cat-pill {{
  font-size: 0.72rem; font-weight: 700;
  background: #7f8c8d; color: #fff;
  padding: 0.2rem 0.55rem; border-radius: 12px; white-space: nowrap;
  margin-top: 0.1rem;
}}
.prompt-q {{ font-size: 0.93rem; font-style: italic; flex: 1; min-width: 200px; color: #2c3e50; }}
.prompt-checks {{
  display: flex; flex-wrap: wrap; gap: 0.4rem;
  margin-bottom: 0.45rem;
}}
.badge-status {{
  font-size: 0.72rem; font-weight: 700;
  padding: 0.2rem 0.6rem; border-radius: 12px;
  white-space: nowrap;
}}
.badge-status.pass {{ background: #d4efdf; color: #1a7a3c; }}
.badge-status.fail {{ background: #fde9e9; color: #a93226; }}
.badge-status.rej-yes {{ background: #d4efdf; color: #1a7a3c; }}
.badge-status.rej-no  {{ background: #fde9e9; color: #a93226; }}
.prompt-meta {{ font-size: 0.79rem; color: #777; margin-bottom: 0.5rem; }}
.prompt-meta code {{ font-size: 0.79rem; background: #f0f4f9; padding: 0.1rem 0.3rem; border-radius: 3px; color: #1b4f72; }}
/* ── SQL block ── */
.sql-details {{ margin-top: 0.3rem; }}
.sql-details summary {{
  cursor: pointer; user-select: none;
  font-size: 0.82rem; color: #1b4f72; font-weight: 500;
}}
.sql-details summary:hover {{ text-decoration: underline; }}
pre.sql-block {{
  background: #1a1a2e; color: #e8f4fd;
  padding: 0.9rem 1rem; border-radius: 6px;
  font-size: 0.8rem; overflow-x: auto;
  white-space: pre-wrap; word-break: break-word;
  margin: 0.5rem 0 0; line-height: 1.55;
}}
/* ── findings box ── */
.findings-box {{
  background: #fff; border: 1px solid #dde3ea; border-radius: 8px;
  padding: 1.2rem 1.5rem; margin-bottom: 2rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}
.findings-box h3 {{ margin: 0 0 0.6rem; font-size: 0.95rem; color: #0d1b2a; }}
.findings-box ul {{ margin: 0; padding-left: 1.3rem; font-size: 0.88rem; line-height: 1.8; color: #333; }}
footer {{
  text-align: center; font-size: 0.78rem; color: #999; padding: 1.5rem;
}}
</style>
</head>
<body>
<header>
  <h1>Grid Copilot &mdash; Table III Batch Validation Report</h1>
  <div class="sub">
    Model: <strong>{e(data['model'])}</strong> &nbsp;|&nbsp;
    Run ID: <strong>{e(data['run_id'])}</strong> &nbsp;|&nbsp;
    Prompts: <strong>20 valid + 10 invalid = 30 total</strong>
  </div>
</header>

<nav>
  <a href="#summary">Summary</a>
  <a href="#table3">Table III</a>
  <a href="#valid">Valid Prompts</a>
  <a href="#invalid">Invalid Prompts</a>
  <a href="#findings">Findings</a>
</nav>

<main>

<!-- ── metric summary ── -->
<h2 id="summary">Metric Summary</h2>
<div class="metric-grid">
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if sv_n==sv_d else '#e67e22'}">
    <div class="metric-val">{t3['sql_validity']}</div>
    <div class="metric-title">SQL Validity</div>
    <div class="metric-sub">Syntactically valid PostgreSQL</div>
    {score_bar(sv_n, sv_d)}
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if vc_n==vc_d else '#e67e22'}">
    <div class="metric-val">{t3['view_compliance']}</div>
    <div class="metric-title">View Compliance</div>
    <div class="metric-sub">Uses only approved KPI views</div>
    {score_bar(vc_n, vc_d)}
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if es_n==es_d else '#e67e22'}">
    <div class="metric-val">{t3['execution_success']}</div>
    <div class="metric-title">Exec Success</div>
    <div class="metric-sub">Executes without DB error</div>
    {score_bar(es_n, es_d)}
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if sc_n==sc_d else '#e67e22'}">
    <div class="metric-val">{t3['semantic_correctness']}</div>
    <div class="metric-title">Semantic</div>
    <div class="metric-sub">Retrieves intended KPI view</div>
    {score_bar(sc_n, sc_d)}
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if iq_n==iq_d else '#e67e22'}">
    <div class="metric-val">{t3['invalid_query_rejection']}</div>
    <div class="metric-title">Rejection Rate</div>
    <div class="metric-sub">Invalid prompts rejected</div>
    {score_bar(iq_n, iq_d)}
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if hall_rate=='0%' else '#e67e22'}">
    <div class="metric-val">{e(hall_rate)}</div>
    <div class="metric-title">Halluc. Rate</div>
    <div class="metric-sub">Non-existing field / view refs</div>
  </div>
  <div class="metric-card" style="border-top:3px solid {'#27ae60' if dml_ok else '#e67e22'}">
    <div class="metric-val">{'YES' if dml_ok else 'PARTIAL'}</div>
    <div class="metric-title">DML Blocked</div>
    <div class="metric-sub">INSERT/UPDATE/DELETE/DROP/ALTER/CREATE</div>
  </div>
</div>

<!-- ── Table III ── -->
<h2 id="table3">TABLE III – Batch-Level Validation of LLM-to-SQL Query Generation</h2>
<div class="t3-wrap">
<table class="t3">
  <thead>
    <tr>
      <th style="width:28%">Metric</th>
      <th style="width:52%">Definition</th>
      <th style="width:20%">Result</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>SQL validity</strong></td>
      <td>Generated query is syntactically valid PostgreSQL.</td>
      <td class="result-cell" style="color:#1a7a3c">{t3['sql_validity']}</td>
    </tr>
    <tr>
      <td><strong>Approved-view compliance</strong></td>
      <td>Query uses only approved KPI views and schema fields.</td>
      <td class="result-cell" style="color:#1a7a3c">{t3['view_compliance']}</td>
    </tr>
    <tr>
      <td><strong>Execution success</strong></td>
      <td>Valid query executes without database error.</td>
      <td class="result-cell" style="color:#1a7a3c">{t3['execution_success']}</td>
    </tr>
    <tr>
      <td><strong>Semantic correctness</strong></td>
      <td>Query retrieves the intended KPI, node, time window, or aggregation.</td>
      <td class="result-cell" style="color:#e67e22">{t3['semantic_correctness']}</td>
    </tr>
    <tr>
      <td><strong>Invalid-query rejection</strong></td>
      <td>Unsafe or unsupported prompts are rejected by the validator.</td>
      <td class="result-cell" style="color:#e67e22">{t3['invalid_query_rejection']}</td>
    </tr>
    <tr>
      <td><strong>Hallucinated field/view rate</strong></td>
      <td>Query references a non-existing field or unapproved view.</td>
      <td class="result-cell" style="color:#e67e22">{e(hall_rate)}</td>
    </tr>
    <tr>
      <td><strong>Data-modification rejection</strong></td>
      <td>Data-modification requests blocked (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE).</td>
      <td class="result-cell" style="color:{'#1a7a3c' if dml_ok else '#e67e22'}">{'YES' if dml_ok else 'PARTIAL'}</td>
    </tr>
  </tbody>
</table>
</div>

<!-- ── valid prompts ── -->
<h2 id="valid">Valid Monitoring Prompts (20)</h2>
{valid_cards}

<!-- ── invalid prompts ── -->
<h2 id="invalid">Invalid / Out-of-Scope Prompts (10)</h2>
{invalid_cards}

<!-- ── findings ── -->
<h2 id="findings">Key Findings &amp; Recommendations</h2>
<div class="findings-box">
  <h3>Strengths</h3>
  <ul>
    <li><strong>SQL validity, view compliance, and execution success</strong> were all perfect (20/20). Every generated query was syntactically correct, restricted to the five approved KPI views, and executed without a database error.</li>
    <li><strong>Semantic correctness was 19/20.</strong> The single miss (D01) routed a broad DR-tracking question to <code>v_kpi_run_summary</code> rather than the more granular <code>v_dr_power_summary</code>. The returned KPI value (<code>mean_abs_dr_error</code>) is correct but lacks node-level breakdown.</li>
    <li>Five of six DML prompts (I01–I05) were correctly intercepted by the validator: the LLM wrapped error messages in string literals that triggered the semicolon or <code>CREATE</code> keyword rule.</li>
  </ul>
</div>
<div class="findings-box">
  <h3>Gaps Identified</h3>
  <ul>
    <li><strong>I06 – CREATE backup (not rejected):</strong> The LLM interpreted "create a backup" as "show me the data" and emitted <code>SELECT * FROM v_kpi_run_summary</code>. The intent (DDL) was not fulfilled but the prompt was not flagged.</li>
    <li><strong>I08 – Raw table query (not rejected):</strong> The LLM obeyed the hard constraint (approved views only) and silently substituted <code>v_kpi_run_summary</code> for the forbidden <code>telemetry_iot_raw</code>. The substitution passes validation but the user's intent was never refused.</li>
    <li><strong>I09 – Out-of-domain columns (not rejected):</strong> For a prompt asking for <code>customer_id</code> / <code>billing_address</code>, the LLM aliased <code>node_id</code> and returned <code>NULL</code> columns instead of refusing. Validator accepted it.</li>
    <li><strong>Hallucinated field rate 30%:</strong> Six of 20 valid queries used computed aliases (<code>voltage_violation_count</code>, <code>max_abs_dr_tracking_error</code>, etc.) that are absent from the raw view schema. The checker flags these as hallucinations; they are syntactically valid aggregation aliases.</li>
  </ul>
</div>
<div class="findings-box">
  <h3>Recommendations</h3>
  <ul>
    <li>Add a <strong>pre-generation intent classifier</strong> that rejects prompts containing schema-modification verbs or non-KPI entity names (customer, billing, topology) before reaching the LLM.</li>
    <li>Extend the hallucination checker's <strong>column whitelist</strong> to accept common SQL aggregate aliases so false positives from <code>COUNT(*) AS x</code> are not flagged.</li>
    <li>Add a <strong>few-shot routing example</strong> to the LLM prompt that explicitly maps broad DR questions to <code>v_dr_power_summary</code> rather than <code>v_kpi_run_summary</code>.</li>
    <li>Consider a <strong>post-generation intent-mismatch check</strong>: if the prompt contains a DML or DDL verb but the generated SQL is a SELECT, log a warning and ask for human confirmation.</li>
  </ul>
</div>

</main>
<footer>
  Generated by Grid Copilot batch validation &mdash; model {e(data['model'])} &mdash; run {e(data['run_id'])}
</footer>
</body>
</html>"""

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Report written → {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
