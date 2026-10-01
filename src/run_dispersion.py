import argparse

from data.miv import run_miv
from data.miv_history import run_miv_history


IV_METHODS = [
    "combined_50delta",
    "average_50delta",
]


def get_args():
    parser = argparse.ArgumentParser(
        description="Run volatility-dispersion calculations."
    )

    parser.add_argument(
        "--index",
        required=True,
        help="Underlying index, e.g. DJIA, SPX, NDX",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help=(
            "Benchmark/index-option ticker. If omitted, use the configured "
            "benchmark when available; otherwise use the index ticker."
        ),
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Optional explicit constituent universe, e.g. AAPL MSFT NVDA AMZN",
    )
    parser.add_argument(
        "--weighting",
        choices=["auto", "price", "market_cap", "equal"],
        default="auto",
        help="Index weighting method.",
    )
    parser.add_argument(
        "--iv-method",
        choices=IV_METHODS,
        default="combined_50delta",
        help="IV construction method; default = combined_50delta",
    )
    parser.add_argument(
        "--date",
        help="Single signal date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--start",
        help="Historical start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end",
        help="Historical end date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="OptionMetrics maturity in days; default = 30",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=36,
        help="Completed monthly observations for correlation; default = 36",
    )
    parser.add_argument(
        "--membership-file",
        default="data/index_membership.csv",
        help="Optional historical membership CSV fallback",
    )
    parser.add_argument(
        "--output",
        default="data/miv_history.csv",
        help="Output CSV path for historical runs",
    )

    return parser.parse_args()


def print_single_result(summary, details):
    """CLI presentation for one-date MIV output."""
    print("\n=== Marshall MIV ===")
    print(f"Index:               {summary['index']}")
    print(f"Benchmark:           {summary['benchmark']}")
    print(f"Date:                {summary['date']}")
    print(f"Weighting:           {summary['weighting']}")
    print(f"IV method:           {summary['iv_method']}")
    print(f"Correlation window:  {summary['correlation_months']} months")
    print(f"IV maturity:         {summary['iv_days']} days")
    print(
        f"Constituents used:   {summary['constituents_used']} / "
        f"{summary['constituents_expected']}"
    )
    print(f"Weight coverage:     {summary['weight_coverage'] * 100:.2f}%")
    print(f"Benchmark IV:        {summary['index_atm_iv'] * 100:.4f}%")
    print(f"Marshall MIV:        {summary['miv'] * 100:.4f}%")
    print(f"Spread:              {summary['spread'] * 100:.4f} vol pts")

    columns = [
        "ticker",
        "permno",
        "secid",
        "weight",
        "iv",
        "correlation",
        "contribution",
    ]
    available = [column for column in columns if column in details.columns]

    if available:
        print("\n=== Constituents ===")
        formatters = {
            "weight": lambda x: f"{x:.6f}",
            "iv": lambda x: f"{x:.6f}",
            "correlation": lambda x: f"{x:.6f}",
            "contribution": lambda x: f"{x:.6f}",
        }
        formatters = {k: v for k, v in formatters.items() if k in available}
        print(
            details[available].to_string(
                index=False,
                formatters=formatters,
            )
        )

    if (
        summary["constituents_used"] < summary["constituents_expected"]
        or summary["weight_coverage"] < 0.999999
    ):
        print(
            "\nWARNING: incomplete constituent coverage "
            f"({summary['weight_coverage'] * 100:.2f}% of index weight)."
        )


def main():
    args = get_args()

    single_mode = args.date is not None
    history_mode = args.start is not None or args.end is not None

    if single_mode and history_mode:
        raise ValueError("Use either --date OR --start/--end, not both.")

    if single_mode:
        summary, details = run_miv(
            index=args.index,
            benchmark=args.benchmark,
            weighting=args.weighting,
            tickers=args.tickers,
            date=args.date,
            days=args.days,
            months=args.months,
            membership_file=args.membership_file,
            iv_method=args.iv_method,
            verbose=True,
        )
        print_single_result(summary, details)
        return

    if args.start is not None and args.end is not None:
        run_miv_history(
            index=args.index,
            benchmark=args.benchmark,
            weighting=args.weighting,
            tickers=args.tickers,
            start=args.start,
            end=args.end,
            days=args.days,
            months=args.months,
            membership_file=args.membership_file,
            output=args.output,
            iv_method=args.iv_method,
            verbose=True,
        )
        return

    if args.start is not None or args.end is not None:
        raise ValueError("Historical mode requires both --start and --end.")

    raise ValueError("Provide either --date or both --start and --end.")


if __name__ == "__main__":
    main()
