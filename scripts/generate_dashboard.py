import argparse
import os
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate KPI dashboard for a run.")
    parser.add_argument("--run-id", required=True, help="Run identifier.")
    parser.add_argument(
        "--db-url",
        required=False,
        default=os.getenv("DATABASE_URL"),
        help="Postgres URL. Defaults to DATABASE_URL env var.",
    )
    parser.add_argument(
        "--out-dir",
        required=False,
        default="reports",
        help="Output directory for the report.",
    )
    return parser.parse_args()


def render_table(df: pd.DataFrame, title: str) -> str:
    if df.empty:
        body = "<p>No data.</p>"
    else:
        body = df.to_html(index=False, classes="table", border=0)
    return f"<section><h2>{title}</h2>{body}</section>"


def main() -> int:
    args = parse_args()
    if not args.db_url:
        print("ERROR: --db-url or DATABASE_URL is required.")
        return 2

    engine = create_engine(args.db_url)

    run_id = args.run_id
    out_dir = os.path.join(args.out_dir, f"run_{run_id}")
    os.makedirs(out_dir, exist_ok=True)

    kpi_run = pd.read_sql(
        "SELECT * FROM v_kpi_run_summary WHERE run_id = %(run_id)s",
        engine,
        params={"run_id": run_id},
    )
    voltage = pd.read_sql(
        """
        SELECT *
        FROM v_voltage_violations
        WHERE run_id = %(run_id)s
        ORDER BY violation_points DESC, node_id
        LIMIT 50
        """,
        engine,
        params={"run_id": run_id},
    )
    soc = pd.read_sql(
        "SELECT * FROM v_soc_summary WHERE run_id = %(run_id)s",
        engine,
        params={"run_id": run_id},
    )
    dr = pd.read_sql(
        "SELECT * FROM v_dr_power_summary WHERE run_id = %(run_id)s",
        engine,
        params={"run_id": run_id},
    )
    vctrl = pd.read_sql(
        "SELECT * FROM v_voltage_control_summary WHERE run_id = %(run_id)s",
        engine,
        params={"run_id": run_id},
    )

    kpi_run.to_csv(os.path.join(out_dir, "kpi_run_summary.csv"), index=False)
    voltage.to_csv(os.path.join(out_dir, "voltage_violations.csv"), index=False)
    soc.to_csv(os.path.join(out_dir, "soc_summary.csv"), index=False)
    dr.to_csv(os.path.join(out_dir, "dr_power_summary.csv"), index=False)
    vctrl.to_csv(os.path.join(out_dir, "voltage_control_summary.csv"), index=False)

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"UTF-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Run KPI Dashboard</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 24px; color: #111; background: #f6f4ef; }",
        "h1 { margin-bottom: 8px; }",
        ".meta { color: #444; margin-bottom: 20px; }",
        "section { margin-bottom: 28px; padding: 16px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }",
        ".table { width: 100%; border-collapse: collapse; }",
        ".table th, .table td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; }",
        ".table th { background: #fafafa; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>Run KPI Dashboard</h1>",
        f"<div class=\"meta\">Run ID: {run_id} | Generated: {datetime.utcnow().isoformat()}Z</div>",
        render_table(kpi_run, "Run Summary"),
        render_table(voltage, "Voltage Violations (Top 50 Nodes)"),
        render_table(soc, "SOC Summary"),
        render_table(dr, "DR Power Summary"),
        render_table(vctrl, "Voltage Control Summary"),
        "</body>",
        "</html>",
    ]

    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"Dashboard written to: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
