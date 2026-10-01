import argparse

from ...src.data.wrds_connection import get_wrds_connection
from ...src.data.security_lookup import get_secid_from_ticker
from ...src.data.optionmetrics_iv import (
    get_50delta_surface,
    get_average_50delta_iv,
    get_combined_50delta_iv,
    get_forward,
    get_zero_rate,
)


def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ticker",
        required=True,
    )

    parser.add_argument(
        "--date",
        required=True,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
    )

    return parser.parse_args()


def main():
    args = get_args()

    db = get_wrds_connection()

    try:
        secid = get_secid_from_ticker(
            db,
            args.ticker,
        )

        surface = get_50delta_surface(
            db,
            secid,
            args.date,
            args.days,
        )

        average_iv = get_average_50delta_iv(
            surface
        )

        combined_iv = get_combined_50delta_iv(
            db,
            secid,
            args.date,
            args.days,
        )

        forward = get_forward(
            db,
            secid,
            args.date,
            args.days,
        )

        rate = get_zero_rate(
            db,
            args.date,
            args.days,
        )

        print(
            f"\n{args.ticker.upper()} "
            f"{args.date} {args.days}D"
        )

        print(
            f"SECID:        {secid}"
        )

        print(
            f"Call IV:      "
            f"{surface['call_iv'] * 100:.4f}%"
        )

        print(
            f"Put IV:       "
            f"{surface['put_iv'] * 100:.4f}%"
        )

        print(
            f"Average IV:   "
            f"{average_iv * 100:.4f}%"
        )

        print(
            f"Combined IV:  "
            f"{combined_iv * 100:.4f}%"
        )

        print(
            f"Difference:   "
            f"{(combined_iv - average_iv) * 100:.4f}"
            f" vol pts"
        )

        print(
            f"Forward:      {forward:.4f}"
        )

        print(
            f"Zero rate:    {rate * 100:.4f}%"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()