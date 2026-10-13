import argparse
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()


TELEMETRY_COLUMNS = [
    "time",
    "node_id",
    "v_a",
    "v_b",
    "v_c",
    "q_a",
    "q_b",
    "q_c",
    "dv_a",
    "dv_b",
    "dv_c",
    "dq_a",
    "dq_b",
    "dq_c",
    "f_node",
    "fes_node",
    "solve_time_ms",
    "switch_flag",
]

IOT_RAW_COLUMNS = [
    "ts",
    "run_id",
    "step",
    "node_id",
    "device_id",
    "feeder_bus",
    "secondary_bus",
    "control_mode",
    "price_signal_usd_mwh",
    "dr_event_flag",
    "p_ref_kw",
    "p_meas_kw",
    "q_ref_kvar",
    "q_meas_kvar",
    "v_bus_pu",
    "soc_percent",
    "mqtt_topic",
    "message_type",
    "protocol_type",
    "packet_length",
    "latency_ms",
    "jitter_ms",
    "flow_rate_kbps",
    "comm_frequency_hz",
    "src_id",
    "dst_id",
    "anomaly_flag",
    "attack_flag",
    "attack_type",
    "resilience_score_ilrs",
    "resilience_score_slnr",
    "resilience_score_plnr",
    "resilience_score_dslr",
    "voltage_violation_flag",
    "p_tracking_error_kw",
    "q_tracking_error_kvar",
    "stable_duration_sec",
    "unstable_duration_sec",
    "violation_count",
    "max_voltage_deviation_pu",
    "avg_p_tracking_error_kw",
    "avg_q_tracking_error_kvar",
    "max_q_overshoot_kvar",
    "vulnerability_score",
    "vulnerability_rank",
    "worst_node_flag",
    "soc_min_run",
    "soc_avg_run",
    "soc_max_run",
    "dr_event_success_flag",
    "run_summary_status",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Replace telemetry table with CSV data.")
    parser.add_argument("--csv", default=r"C:\Users\Azmee\Downloads\opendss_ae_features_500_decentralized.csv")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres"),
    )
    return parser.parse_args()


def build_telemetry_from_iot_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Map IoT management dataset columns into the legacy telemetry schema."""
    iot_required = {
        "ts",
        "node_id",
        "v_bus_pu",
        "q_meas_kvar",
        "q_tracking_error_kvar",
        "latency_ms",
        "voltage_violation_flag",
    }
    if not iot_required.issubset(set(df.columns)):
        return pd.DataFrame()

    ts_numeric = pd.to_datetime(df["ts"], errors="coerce").astype("int64") / 1_000_000_000
    q_meas = pd.to_numeric(df["q_meas_kvar"], errors="coerce")
    q_err = pd.to_numeric(df["q_tracking_error_kvar"], errors="coerce")
    v_bus = pd.to_numeric(df["v_bus_pu"], errors="coerce")
    latency = pd.to_numeric(df["latency_ms"], errors="coerce")
    switch_flag = pd.to_numeric(df["voltage_violation_flag"], errors="coerce")

    out = pd.DataFrame(
        {
            "time": ts_numeric,
            "node_id": pd.to_numeric(df["node_id"], errors="coerce"),
            "v_a": v_bus,
            "v_b": v_bus,
            "v_c": v_bus,
            "q_a": q_meas,
            "q_b": q_meas,
            "q_c": q_meas,
            "dv_a": (v_bus - 1.0).abs(),
            "dv_b": (v_bus - 1.0).abs(),
            "dv_c": (v_bus - 1.0).abs(),
            "dq_a": q_err,
            "dq_b": q_err,
            "dq_c": q_err,
            "f_node": pd.to_numeric(df.get("resilience_score_ilrs"), errors="coerce"),
            "fes_node": pd.to_numeric(df.get("resilience_score_slnr"), errors="coerce"),
            "solve_time_ms": latency,
            "switch_flag": switch_flag,
        }
    )
    return out


def to_python_scalar(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def load_iot_raw_table(cur, source_df: pd.DataFrame):
    missing_iot = [c for c in IOT_RAW_COLUMNS if c not in source_df.columns]
    if missing_iot:
        print(f"Skipped raw IoT table load (missing columns): {missing_iot}")
        return 0

    raw_df = source_df[IOT_RAW_COLUMNS].copy()
    rows = [tuple(to_python_scalar(value) for value in row) for row in raw_df.itertuples(index=False, name=None)]

    cur.execute("DROP TABLE IF EXISTS public.telemetry_iot_raw;")
    create_columns_sql = ",\n                        ".join(f'"{col}" TEXT' for col in IOT_RAW_COLUMNS)
    cur.execute(
        f"""
        CREATE TABLE public.telemetry_iot_raw (
                        {create_columns_sql}
        );
        """
    )

    if rows:
        insert_columns_sql = ", ".join(f'"{col}"' for col in IOT_RAW_COLUMNS)
        execute_values(
            cur,
            f"""
            INSERT INTO public.telemetry_iot_raw ({insert_columns_sql})
            VALUES %s
            """,
            rows,
            page_size=10000,
        )
    return len(rows)


def main():
    args = parse_args()
    source_df = pd.read_csv(args.csv)
    source_df.columns = [c.strip() for c in source_df.columns]
    df = source_df.copy()

    required_cols = TELEMETRY_COLUMNS.copy()
    if "time" not in df.columns and "t" in df.columns:
        df = df.rename(columns={"t": "time"})

    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        mapped_df = build_telemetry_from_iot_schema(df)
        if mapped_df.empty:
            raise ValueError(f"Missing required columns: {missing_cols}")
        df = mapped_df
    else:
        df = df[required_cols].copy()

    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["time", "node_id"])
    df["node_id"] = df["node_id"].astype("Int64")
    df["switch_flag"] = df["switch_flag"].round().astype("Int64")
    df = df.dropna(subset=["node_id", "switch_flag"])

    rows = [tuple(to_python_scalar(value) for value in row) for row in df.itertuples(index=False, name=None)]

    conn = psycopg2.connect(args.db_url)
    try:
        with conn.cursor() as cur:
            raw_rows_loaded = load_iot_raw_table(cur, source_df)

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'telemetry'
                ORDER BY ordinal_position;
                """
            )
            existing_columns = [row[0] for row in cur.fetchall()]

            expected_columns = TELEMETRY_COLUMNS.copy()
            needs_recreate = bool(existing_columns) and existing_columns != expected_columns

            if needs_recreate:
                cur.execute("DROP TABLE IF EXISTS public.telemetry CASCADE;")

            if not existing_columns or needs_recreate:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.telemetry (
                        "time" DOUBLE PRECISION,
                        node_id BIGINT,
                        v_a DOUBLE PRECISION,
                        v_b DOUBLE PRECISION,
                        v_c DOUBLE PRECISION,
                        q_a DOUBLE PRECISION,
                        q_b DOUBLE PRECISION,
                        q_c DOUBLE PRECISION,
                        dv_a DOUBLE PRECISION,
                        dv_b DOUBLE PRECISION,
                        dv_c DOUBLE PRECISION,
                        dq_a DOUBLE PRECISION,
                        dq_b DOUBLE PRECISION,
                        dq_c DOUBLE PRECISION,
                        f_node DOUBLE PRECISION,
                        fes_node DOUBLE PRECISION,
                        solve_time_ms DOUBLE PRECISION,
                        switch_flag INTEGER
                    );
                    """
                )

            cur.execute(
                """
                TRUNCATE TABLE public.telemetry;
                """,
            )
            if rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO public.telemetry (
                        "time", node_id, v_a, v_b, v_c, q_a, q_b, q_c,
                        dv_a, dv_b, dv_c, dq_a, dq_b, dq_c, f_node, fes_node,
                        solve_time_ms, switch_flag
                    )
                    VALUES %s
                    """,
                    rows,
                    page_size=10000,
                )
        conn.commit()
    finally:
        conn.close()

    if needs_recreate:
        print("Telemetry table schema was recreated to match required CSV columns (dependent views were dropped).")
    if raw_rows_loaded:
        print(f"Inserted raw IoT rows into public.telemetry_iot_raw: {raw_rows_loaded}")
    print(f"Inserted rows: {len(rows)}")


if __name__ == "__main__":
    main()
