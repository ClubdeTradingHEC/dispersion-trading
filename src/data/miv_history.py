from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection
from .security_lookup import get_index_secid

from .miv import (
    compute_miv_for_date,
    resolve_index_settings,
    load_optional_membership,
)


# ============================================================
# SIGNAL DATES
# ============================================================


def get_signal_dates(
    db,
    benchmark,
    start_date,
    end_date,
):
    """
    Return actual benchmark trading dates from OptionMetrics.
    """

    benchmark = (
        str(benchmark)
        .upper()
        .strip()
    )

    secid = get_index_secid(
        db=db,
        ticker=benchmark,
    )

    dates = db.raw_sql(
        f"""
        SELECT DISTINCT
            date
        FROM optionm.secprd
        WHERE secid = {secid}
          AND date >= '{start_date}'
          AND date <= '{end_date}'
        ORDER BY date
        """,
        date_cols=["date"],
    )

    if dates.empty:
        return []

    return dates[
        "date"
    ].tolist()


# ============================================================
# HISTORY ENGINE
# ============================================================


def _compute_miv_history_diagnostic(
    db,
    index,
    start,
    end,
    benchmark=None,
    days=30,
    months=36,
    membership=None,
    weighting="auto",
    tickers=None,
    iv_method="combined_50delta",
    verbose=True,
):
    """
    Compute daily Marshall MIV and dispersion spread
    over a date range.

    Does not manage the WRDS connection and does not write files.
    """

    start_date = pd.Timestamp(
        start
    )

    end_date = pd.Timestamp(
        end
    )

    if end_date < start_date:
        raise ValueError(
            "end must be greater than or equal to start."
        )

    settings = resolve_index_settings(
        index=index,
        benchmark=benchmark,
        weighting=weighting,
    )

    index = settings[
        "index"
    ]

    benchmark = settings[
        "benchmark"
    ]

    weighting = settings[
        "weighting"
    ]

    signal_dates = get_signal_dates(
        db=db,
        benchmark=benchmark,
        start_date=start_date.date(),
        end_date=end_date.date(),
    )

    if not signal_dates:
        return pd.DataFrame()

    if verbose:
        print(
            "\n=== MIV History ==="
        )

        print(
            f"Index:        {index}"
        )

        print(
            f"Benchmark:    {benchmark}"
        )

        print(
            f"Weighting:    {weighting}"
        )

        print(
            f"IV method:    {iv_method}"
        )

        print(
            f"Start:        {start_date.date()}"
        )

        print(
            f"End:          {end_date.date()}"
        )

        print(
            f"Trading days: {len(signal_dates)}"
        )

        print()

    history = []

    for i, signal_date in enumerate(
        signal_dates,
        start=1,
    ):
        signal_date = pd.Timestamp(
            signal_date
        )

        if verbose:
            print(
                f"[{i}/{len(signal_dates)}] "
                f"{signal_date.date()}"
            )

        try:
            summary, _ = compute_miv_for_date(
                db=db,
                membership=membership,
                index=index,
                benchmark=benchmark,
                date=signal_date,
                days=days,
                months=months,
                weighting=weighting,
                tickers=tickers,
                iv_method=iv_method,
                verbose=False,
            )

            history.append(
                summary
            )

            if verbose:
                print(
                    f"    {benchmark} IV: "
                    f"{summary['index_atm_iv'] * 100:.4f}%"
                )

                print(
                    f"    MIV:           "
                    f"{summary['miv'] * 100:.4f}%"
                )

                print(
                    f"    Spread:        "
                    f"{summary['spread'] * 100:.4f}%"
                )

                print(
                    f"    Coverage:      "
                    f"{summary['weight_coverage'] * 100:.2f}%"
                )

                print(
                    f"    Constituents:  "
                    f"{summary['constituents_used']} / "
                    f"{summary['constituents_expected']}"
                )

        except ValueError as e:
            if verbose:
                print(
                    f"    Skipped: {e}"
                )

    if not history:
        return pd.DataFrame()

    return (
        pd.DataFrame(
            history
        )
        .sort_values(
            "date"
        )
        .reset_index(
            drop=True
        )
    )


def compute_miv_history(db, index, start, end, benchmark=None, days=30, months=36,
                        membership=None, weighting="auto", tickers=None,
                        iv_method="combined_50delta", verbose=True,
                        engine="diagnostic", research_config=None):
    """Use Kevin's original calculation by default; batching remains opt-in."""
    if engine == "diagnostic":
        return _compute_miv_history_diagnostic(db, index, start, end, benchmark, days,
            months, membership, weighting, tickers, iv_method, verbose)
    if engine != "batched":
        raise ValueError("history engine must be batched or diagnostic")
    if tickers is not None or iv_method != "combined_50delta" or months != 36:
        raise ValueError("Non-baseline exploratory history requires engine='diagnostic'")
    from dataclasses import replace
    from src.research.config import Config, IndexSpec
    from src.research.wrds_client import extract
    from src.research.batching import compute_to_disk
    settings = resolve_index_settings(index, benchmark, weighting)
    cfg = Config.read(research_config or "configs/research.json")
    secid = get_index_secid(db, settings["benchmark"])
    spec = IndexSpec(settings["index"], settings["benchmark"], settings["weighting"], secid)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="dispersion-membership-") as temporary:
        if membership is not None and settings["index"] != "SPX":
            raise ValueError("Set the historical membership_csv in research_config for this index")
        configured = next((item for item in cfg.indices if item["name"] == spec.name), None)
        if configured:
            spec.membership_csv = configured.get("membership_csv")
        cfg = replace(cfg, entry_start=str(pd.Timestamp(start).date()), entry_end=str(pd.Timestamp(end).date()),
                      horizons=[days], indices=[spec.__dict__])
        raw = extract(db, cfg, "data/wrds", progress=print if verbose else lambda _: None, materialize=False)
        target = Path("data/reports/kevin_history")
        compute_to_disk(raw, cfg, target, batch_sessions=63)
        frame = pd.read_parquet(target / "measurements.parquet")
        frame = frame.loc[frame.basket == "full"].copy()
        if frame.empty:
            return pd.DataFrame()
        frame = frame.rename(columns={"index_iv": "index_atm_iv", "n_selected": "constituents_used"})
        frame["benchmark"] = spec.benchmark
        frame["weighting"] = spec.weighting
        frame["iv_method"] = iv_method
        frame["iv_days"], frame["correlation_months"] = days, months
        frame["weight_coverage"] = frame["original_cap_coverage"]
        frame["constituents_expected"] = frame["n_original"]
        frame["miv"] = frame.get("miv", float("nan"))
        frame["spread"] = frame.get("spread", float("nan"))
        frame["spread_vol_bps"] = frame["spread"] * 10000
        # Keep exclusion statuses and empty values rather than hide failed dates.
        return frame.sort_values("date").reset_index(drop=True)


# ============================================================
# PUBLIC FUNCTION
# ============================================================


def run_miv_history(
    index,
    start,
    end,
    benchmark=None,
    days=30,
    months=36,
    membership_file="data/index_membership.csv",
    output="data/miv_history.csv",
    weighting="auto",
    tickers=None,
    iv_method="combined_50delta",
    verbose=True,
    engine="diagnostic",
    research_config=None,
):
    """
    Public historical MIV function.

    Manages:
        - configuration
        - optional membership
        - WRDS connection
        - optional CSV output
    """

    settings = resolve_index_settings(
        index=index,
        benchmark=benchmark,
        weighting=weighting,
    )

    membership = load_optional_membership(
        membership_file=membership_file,
        tickers=tickers,
    )

    db = get_wrds_connection(cache=False)

    try:
        history = compute_miv_history(
            db=db,
            index=settings["index"],
            benchmark=settings["benchmark"],
            start=start,
            end=end,
            days=days,
            months=months,
            membership=membership,
            weighting=settings["weighting"],
            tickers=tickers,
            iv_method=iv_method,
            verbose=verbose,
            engine=engine, research_config=research_config,
        )

    finally:
        db.close()

    if history.empty:
        if verbose:
            print(
                "\nNo successful observations."
            )

        return history

    # --------------------------------------------------------
    # Optional output
    # --------------------------------------------------------

    if output is not None:
        output_path = Path(
            output
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        history.to_csv(
            output_path,
            index=False,
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    if verbose:
        print(
            "\n=== History Summary ==="
        )

        print(
            f"Observations:       "
            f"{len(history)}"
        )

        print(
            f"Average index IV:   "
            f"{history['index_atm_iv'].mean() * 100:.4f}%"
        )

        print(
            f"Average MIV:        "
            f"{history['miv'].mean() * 100:.4f}%"
        )

        print(
            f"Average spread:     "
            f"{history['spread'].mean() * 100:.4f}%"
        )

        print(
            f"Min spread:         "
            f"{history['spread'].min() * 100:.4f}%"
        )

        print(
            f"Max spread:         "
            f"{history['spread'].max() * 100:.4f}%"
        )

        print(
            f"Average coverage:   "
            f"{history['weight_coverage'].mean() * 100:.2f}%"
        )

        if output is not None:
            print(
                f"\nSaved to: {output}"
            )

    return history
