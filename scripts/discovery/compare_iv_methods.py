import argparse
import pandas as pd

from ...src.data.wrds_connection import get_wrds_connection
from .iv_lookup import (
    get_50delta_surface,
    get_average_50delta_iv,
    get_combined_50delta_iv,
)


def get_args():
    parser = argparse.ArgumentParser(
        description="Compare average vs combined-premium IV methods."
    )

    parser.add_argument(
        "--ticker",
        required=True,
        type=str,
        help="Ticker, e.g. AAPL, DJX",
    )

    parser.add_argument(
        "--secid",
        required=True,
        type=int,
        help="OptionMetrics SECID",
    )

    parser.add_argument(
        "--start",
        required=True,
        type=str,
        help="Start date YYYY-MM-DD",
    )

    parser.add_argument(
        "--end",
        required=True,
        type=str,
        help="End date YYYY-MM-DD",
    )

    parser.add_argument(
        "--days",
        default=30,
        type=int,
    )

    return parser.parse_args()


def main():
    args = get_args()

    db = get_wrds_connection()

    rows = []

    try:
        dates = pd.date_range(
            start=args.start,
            end=args.end,
            freq="B",
        )

        for date in dates:
            date_str = date.strftime("%Y-%m-%d")

            try:
                surface = get_50delta_surface(
                    db=db,
                    secid=args.secid,
                    date=date_str,
                    days=args.days,
                )

                average_iv = get_average_50delta_iv(
                    surface
                )

                combined_iv, diagnostics = (
                    get_combined_50delta_iv(
                        db=db,
                        secid=args.secid,
                        date=date_str,
                        days=args.days,
                    )
                )

                difference = (
                    combined_iv - average_iv
                )

                rows.append(
                    {
                        "date": date_str,
                        "ticker": args.ticker.upper(),
                        "secid": args.secid,
                        "call_iv": surface["call_iv"],
                        "put_iv": surface["put_iv"],
                        "average_iv": average_iv,
                        "combined_iv": combined_iv,
                        "difference": difference,
                        "abs_difference": abs(difference),
                        "forward": diagnostics["forward"],
                        "zero_rate": diagnostics["zero_rate"],
                    }
                )

                print(
                    f"{date_str} | "
                    f"avg={average_iv * 100:.4f}% | "
                    f"combined={combined_iv * 100:.4f}% | "
                    f"diff={difference * 100:.6f} vol pts"
                )

            except Exception as e:
                print(
                    f"{date_str} | skipped | {e}"
                )

        if not rows:
            print("\nNo valid observations.")
            return

        df = pd.DataFrame(
            rows
        )

        print("\n=== Summary ===")

        print(
            f"Observations:              "
            f"{len(df)}"
        )

        print(
            f"Mean difference:           "
            f"{df['difference'].mean() * 100:.6f} vol pts"
        )

        print(
            f"Mean absolute difference:  "
            f"{df['abs_difference'].mean() * 100:.6f} vol pts"
        )

        print(
            f"Median absolute difference:"
            f" {df['abs_difference'].median() * 100:.6f} vol pts"
        )

        print(
            f"95th pct abs difference:   "
            f"{df['abs_difference'].quantile(0.95) * 100:.6f} vol pts"
        )

        print(
            f"Maximum abs difference:    "
            f"{df['abs_difference'].max() * 100:.6f} vol pts"
        )

        idx = (
            df["abs_difference"]
            .idxmax()
        )

        worst = df.loc[
            idx
        ]

        print("\n=== Largest Difference ===")

        print(
            f"Date:          {worst['date']}"
        )

        print(
            f"Call IV:       "
            f"{worst['call_iv'] * 100:.4f}%"
        )

        print(
            f"Put IV:        "
            f"{worst['put_iv'] * 100:.4f}%"
        )

        print(
            f"Average IV:    "
            f"{worst['average_iv'] * 100:.4f}%"
        )

        print(
            f"Combined IV:   "
            f"{worst['combined_iv'] * 100:.4f}%"
        )

        print(
            f"Difference:    "
            f"{worst['difference'] * 100:.6f} vol pts"
        )

        output_file = (
            f"iv_method_comparison_"
            f"{args.ticker.upper()}_"
            f"{args.start}_"
            f"{args.end}.csv"
        )

        df.to_csv(
            output_file,
            index=False,
        )

        print(
            f"\nSaved results to {output_file}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()