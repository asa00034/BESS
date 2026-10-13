import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute SQL and package results.")
    parser.add_argument("--sql", type=str, help="Raw SQL string to execute")
    parser.add_argument("--sql-file", type=str, help="Path to .sql file")
    parser.add_argument("--db-url", type=str, default=None, help="PostgreSQL connection URL")
    parser.add_argument("--question-id", type=str, default="query", help="Identifier used in output file names")
    parser.add_argument(
        "--format",
        type=str,
        default="json",
        choices=["json", "csv", "both"],
        help="Output format",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="outputs/sql results",
        help="Directory for SQL execution outputs",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=1000,
        help="Max rows stored in packaged output file",
    )
    return parser.parse_args()


def read_sql(args: argparse.Namespace) -> str:
    if args.sql:
        return args.sql.strip()
    if args.sql_file:
        return Path(args.sql_file).read_text(encoding="utf-8").strip()
    raise ValueError("Provide --sql or --sql-file")


def safe_name(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "query"


def main() -> None:
    load_dotenv()
    args = parse_args()

    sql = read_sql(args)
    db_url = args.db_url or os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(args.question_id)

    engine = create_engine(db_url, connect_args={"connect_timeout": 8})
    start = time.perf_counter()
    status = "success"
    error_text = None

    try:
        df = pd.read_sql(sql, engine)
    except Exception as error:
        status = "failed"
        error_text = str(error)
        df = pd.DataFrame()

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    row_count = int(len(df))
    columns = list(df.columns)
    packaged = df.head(max(args.max_rows, 0))

    json_path = out_dir / f"{stem}.json"
    csv_path = out_dir / f"{stem}.csv"
    metadata_path = out_dir / f"{stem}.meta.json"

    if status == "success":
        if args.format in {"json", "both"}:
            payload = {
                "question_id": args.question_id,
                "status": status,
                "row_count": row_count,
                "columns": columns,
                "execution_time_ms": elapsed_ms,
                "sql": sql,
                "rows": packaged.to_dict(orient="records"),
            }
            json_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

        if args.format in {"csv", "both"}:
            packaged.to_csv(csv_path, index=False)

    metadata = {
        "question_id": args.question_id,
        "status": status,
        "row_count": row_count,
        "columns": columns,
        "execution_time_ms": elapsed_ms,
        "output_json": str(json_path).replace("\\", "/") if args.format in {"json", "both"} and status == "success" else None,
        "output_csv": str(csv_path).replace("\\", "/") if args.format in {"csv", "both"} and status == "success" else None,
        "error": error_text,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
