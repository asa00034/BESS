import argparse
import json
import re
from pathlib import Path


DEFAULT_THRESHOLDS = {
    "voltage_min_pu": 0.95,
    "voltage_max_pu": 1.05,
    "soc_low": 0.20,
    "soc_high": 0.90,
    "dr_abs_error_warning": 0.05,
    "dr_abs_error_severe": 0.10,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate operational constraints over SQL outputs.")
    parser.add_argument("--input", required=True, help="Path to SQL result JSON produced by run sql.py")
    parser.add_argument(
        "--constraints",
        default="agentic_ai/M2/operational constraints.md",
        help="Path to constraints markdown or json",
    )
    parser.add_argument("--question-id", default="query", help="Question identifier for output file naming")
    parser.add_argument("--out-dir", default="outputs/constraint checks", help="Output directory")
    return parser.parse_args()


def load_thresholds(constraints_path: Path) -> dict:
    if constraints_path.suffix.lower() == ".json":
        obj = json.loads(constraints_path.read_text(encoding="utf-8"))
        merged = {**DEFAULT_THRESHOLDS, **obj}
        return merged

    text = constraints_path.read_text(encoding="utf-8")
    merged = dict(DEFAULT_THRESHOLDS)

    voltage_match = re.search(r"(0\.\d+)\s*to\s*(1\.\d+).*p\.u", text, flags=re.IGNORECASE)
    if voltage_match:
        merged["voltage_min_pu"] = float(voltage_match.group(1))
        merged["voltage_max_pu"] = float(voltage_match.group(2))

    soc_match = re.search(r"(0\.\d+)\s*to\s*(0\.\d+).*(policy|preferred)", text, flags=re.IGNORECASE)
    if soc_match:
        merged["soc_low"] = float(soc_match.group(1))
        merged["soc_high"] = float(soc_match.group(2))

    return merged


def safe_max(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    return max(clean) if clean else None


def safe_min(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    return min(clean) if clean else None


def evaluate(payload: dict, thresholds: dict) -> dict:
    rows = payload.get("rows", [])
    columns = set(payload.get("columns", []))

    has_voltage = any(
        name in columns
        for name in [
            "voltage_pu",
            "deviation_pu",
            "violation_count",
            "violation_event_count",
            "max_deviation_pu",
            "avg_deviation_pu",
            "v_violation_count",
        ]
    )
    has_soc = any(name in columns for name in ["soc_min", "soc_mean", "soc_max"])
    has_dr = any(name in columns for name in ["abs_error", "max_abs_error", "mean_abs_error", "mean_abs_dr_error"])
    has_q = any(name in columns for name in ["q_violation", "q_violation_count"])

    voltage_violation_duration = 0
    max_deviation = None
    if "deviation_pu" in columns:
        deviations = [row.get("deviation_pu") for row in rows]
        max_deviation = safe_max(deviations)
        voltage_violation_duration = len([value for value in deviations if value is not None and float(value) > 0])
    elif "max_deviation_pu" in columns:
        deviations = [row.get("max_deviation_pu") for row in rows]
        max_deviation = safe_max(deviations)
        counts = [
            row.get("violation_event_count", row.get("violation_count", 0))
            for row in rows
        ]
        voltage_violation_duration = int(sum(float(value) for value in counts if value is not None))
    elif "v_violation_count" in columns:
        counts = [row.get("v_violation_count", 0) for row in rows]
        voltage_violation_duration = int(sum(float(value) for value in counts if value is not None))

    soc_binding_low = False
    soc_binding_high = False
    soc_min_value = None
    soc_max_value = None
    if has_soc:
        mins = [row.get("soc_min") for row in rows]
        maxs = [row.get("soc_max") for row in rows]
        soc_min_value = safe_min(mins)
        soc_max_value = safe_max(maxs)
        if soc_min_value is not None and soc_min_value < thresholds["soc_low"]:
            soc_binding_low = True
        if soc_max_value is not None and soc_max_value > thresholds["soc_high"]:
            soc_binding_high = True

    q_overshoot_flags = False
    if "q_violation" in columns:
        q_overshoot_flags = any(bool(row.get("q_violation")) for row in rows)
    elif "q_violation_count" in columns:
        q_overshoot_flags = any((row.get("q_violation_count") or 0) > 0 for row in rows)

    dr_max = None
    if "abs_error" in columns:
        dr_max = safe_max([row.get("abs_error") for row in rows])
    elif "max_abs_error" in columns:
        dr_max = safe_max([row.get("max_abs_error") for row in rows])
    elif "mean_abs_dr_error" in columns:
        dr_max = safe_max([row.get("mean_abs_dr_error") for row in rows])

    if payload.get("row_count", 0) == 0:
        label = "constrained"
        rationale = "No rows returned; evidence is constrained for decisioning."
    elif voltage_violation_duration > 0 and (max_deviation is not None and max_deviation >= 0.10):
        label = "unstable"
        rationale = "Voltage violations and severe deviation indicate unstable condition."
    elif voltage_violation_duration > 0 or soc_binding_low or soc_binding_high or q_overshoot_flags:
        label = "vulnerable"
        rationale = "Constraint indicators exist but not in severe unstable range."
    elif dr_max is not None and dr_max >= thresholds["dr_abs_error_severe"]:
        label = "vulnerable"
        rationale = "Tracking error is high, indicating vulnerable operation."
    else:
        label = "stable"
        rationale = "No major violations found in available evidence."

    summary = {
        "label": label,
        "rationale": rationale,
        "metrics": {
            "row_count": payload.get("row_count", 0),
            "voltage_violation_duration": voltage_violation_duration,
            "max_deviation_pu": max_deviation,
            "soc_min": soc_min_value,
            "soc_max": soc_max_value,
            "soc_binding_low": soc_binding_low,
            "soc_binding_high": soc_binding_high,
            "q_overshoot_flags": q_overshoot_flags,
            "max_abs_tracking_error": dr_max,
        },
        "features_detected": {
            "voltage": has_voltage,
            "soc": has_soc,
            "dr": has_dr,
            "reactive": has_q,
        },
        "thresholds": thresholds,
    }
    return summary


def main() -> None:
    args = parse_args()
    in_path = Path(args.input)
    constraints_path = Path(args.constraints)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    thresholds = load_thresholds(constraints_path)
    decision = evaluate(payload, thresholds)

    output = {
        "question_id": args.question_id,
        "input_file": str(in_path).replace("\\", "/"),
        "decision": decision,
    }

    output_path = out_dir / f"{args.question_id}.decision.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
