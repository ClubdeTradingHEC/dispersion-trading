"""Remove the legacy per-straddle fixed stress and reconcile 2019 cost exports."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


MARSHALL_SIGNAL_HURDLE_VOL_POINTS = 4.09
ES_HALF_TICK_USD_PER_CONTRACT = 6.25  # Assumption per one-way ES execution. Not calibrated.
OPTION_COMMISSION_USD_PER_CONTRACT = 0.65


def crosses_marshall_hurdle(ioiv, miv):
    """Evaluate the research hurdle once on the index signal, with both IVs in decimals."""
    return abs(ioiv - miv) > MARSHALL_SIGNAL_HURDLE_VOL_POINTS / 100


def option_pair_execution_cost(quantity, one_way_half_spread_usd, scenario="base"):
    """Dollar cost per execution. Input half-spread includes the contract multiplier."""
    spread_factor = {"base": 1, "observed_stress": 2}[scenario]
    commission = 2 * OPTION_COMMISSION_USD_PER_CONTRACT
    return abs(quantity) * (spread_factor * one_way_half_spread_usd + commission)


def es_hedge_cost(contracts_traded):
    return abs(contracts_traded) * ES_HALF_TICK_USD_PER_CONTRACT


def clean_options(frame):
    """Preserve observed spread costs and remove all legacy fixed-stress columns."""
    obsolete = [column for column in frame if 'fixed_stress' in column.lower()]
    return frame.drop(columns=obsolete)


def compare_exports(ours, theirs, keys, fields, tolerance):
    # Normalize table IDs and dates while keeping identity checks on the declared keys.
    ours, theirs = ours.copy(), theirs.copy()
    for frame in (ours, theirs):
        for key in keys:
            if key == "date":
                frame[key] = pd.to_datetime(frame[key], errors="raise").dt.date
            elif key in {"secid", "permno", "call_optionid", "put_optionid"}:
                frame[key] = pd.to_numeric(frame[key], errors="raise").astype("Int64")
            elif key == "ticker":
                frame[key] = frame[key].astype("string").str.upper().str.strip()
        if frame[keys].isna().any().any():
            raise ValueError(f"Missing values in comparison keys: {keys}")
        for field in fields:
            frame[field] = pd.to_numeric(frame[field], errors="raise")
    detail = ours[keys + fields].merge(
        theirs[keys + fields], on=keys, how="outer", validate="one_to_one",
        suffixes=("_kevin", "_rami"), indicator="coverage",
    )
    matched = detail["coverage"].eq("both")
    summary = []
    for field in fields:
        left, right = detail[f"{field}_kevin"], detail[f"{field}_rami"]
        detail[f"{field}_delta_rami_minus_kevin"] = right - left
        agrees = matched & np.isfinite(left) & np.isfinite(right) & (right - left).abs().le(tolerance)
        detail[f"{field}_agrees"] = agrees
        deviations = (right[matched] - left[matched]).abs().dropna()
        summary.append({
            "field": field,
            "matched": int(matched.sum()),
            "kevin_only": int(detail.coverage.eq("left_only").sum()),
            "rami_only": int(detail.coverage.eq("right_only").sum()),
            "matched_outside_tolerance_or_invalid": int((matched & ~agrees).sum()),
            "median_abs_diff": deviations.median(),
            "max_abs_diff": deviations.max(),
            "validated": bool(len(detail) and agrees.all()),
        })
    return detail, pd.DataFrame(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    clean = commands.add_parser("clean-options")
    clean.add_argument("--input", type=Path, required=True)
    clean.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--ours", type=Path, required=True)
    compare.add_argument("--rami", type=Path, required=True)
    compare.add_argument("--keys", nargs="+", required=True)
    compare.add_argument("--fields", nargs="+", required=True)
    compare.add_argument("--tolerance", type=float, default=1e-6)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "clean-options":
        if args.input.resolve() == args.output.resolve():
            parser.error("Use a separate output path so the original 2019 CSV is preserved.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Read as strings to preserve numeric formatting and identifier precision.
        result = clean_options(pd.read_csv(args.input, dtype=str, keep_default_na=False))
        temporary = args.output.with_suffix(".tmp")
        result.to_csv(temporary, index=False)
        temporary.replace(args.output)
        print(f"{len(result):,} rows written to {args.output}")
        return
    if not np.isfinite(args.tolerance) or args.tolerance < 0:
        parser.error("--tolerance must be finite and nonnegative")
    if set(args.keys) & set(args.fields):
        parser.error("--keys and --fields must be disjoint")
    detail, summary = compare_exports(
        pd.read_csv(args.ours), pd.read_csv(args.rami), args.keys, args.fields, args.tolerance,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(args.output / "reconciliation_detail.csv", index=False)
    summary.to_csv(args.output / "reconciliation_summary.csv", index=False)
    print(summary.to_string(index=False))
    if not summary.validated.all():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
