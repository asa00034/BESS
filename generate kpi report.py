import argparse
import json
import os
from datetime import timedelta

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True, help="Run identifier")
    p.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres"),
        help="PostgreSQL connection string",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    engine = create_engine(args.db_url)

    with engine.begin() as conn:
        # Violations count + duration
        v = pd.read_sql(
            text("""
                SELECT ts, device_id, violation
                FROM v_voltage_violations
                WHERE run_id = :run_id AND violation IN ('UNDER','OVER')
                ORDER BY ts
            """),
            conn,
            params={"run_id": args.run_id},
        )

        violation_count = int(len(v))
        violation_duration = 0.0
        worst_node = None

        if not v.empty:
            v["ts"] = pd.to_datetime(v["ts"], utc=True)
            v = v.sort_values("ts")
            # approximate duration as consecutive gaps
            deltas = v["ts"].diff().dt.total_seconds().fillna(0)
            violation_duration = float(deltas.sum())
            worst_node = v["device_id"].value_counts().idxmax()

        soc = pd.read_sql(
            text("""
                SELECT MIN(soc) AS soc_min, AVG(soc) AS soc_avg
                FROM telemetry WHERE run_id = :run_id AND soc IS NOT NULL
            """),
            conn,
            params={"run_id": args.run_id},
        ).iloc[0]

        tracking = pd.read_sql(
            text("""
                SELECT
                    AVG(pref - pmeas) AS pref_pmeas_err,
                    AVG(qref - qmeas) AS qref_qmeas_err
                FROM telemetry
                WHERE run_id = :run_id
            """),
            conn,
            params={"run_id": args.run_id},
        ).iloc[0]

    report = {
        "run_id": args.run_id,
        "violation_count": violation_count,
        "violation_duration_seconds": violation_duration,
        "worst_node": worst_node,
        "soc_avg": float(soc["soc_avg"]) if pd.notna(soc["soc_avg"]) else None,
        "soc_min": float(soc["soc_min"]) if pd.notna(soc["soc_min"]) else None,
        "pref_pmeas_avg_error": float(tracking["pref_pmeas_err"]) if pd.notna(tracking["pref_pmeas_err"]) else None,
        "qref_qmeas_avg_error": float(tracking["qref_qmeas_err"]) if pd.notna(tracking["qref_qmeas_err"]) else None,
    }

    os.makedirs("reports", exist_ok=True)
    out_path = f"reports/run_{args.run_id}_kpi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved KPI report: {out_path}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())