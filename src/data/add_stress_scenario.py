
from pathlib import Path

import pandas as pd


def main():
    input_path = Path(
        "data/transaction_costs/top30_2019/simulator_costs.csv"
    )

    output_path = Path(
        "data/transaction_costs/top30_2019/"
        "simulator_costs_final.csv"
    )

    df = pd.read_csv(input_path)

    # Fixed stress assumption:
    # 4.09 volatility points per one-way straddle execution.
    df["fixed_stress_cost_vol_points"] = 4.09

    df["fixed_stress_cost_usd"] = (
        4.09
        * df["vega_usd_per_vol_point"]
        * df["contract_size"]
    )

    # Two option contracts: one call and one put.
    df["fixed_stress_with_commission_usd"] = (
        df["fixed_stress_cost_usd"]
        + df["commission_usd"]
    )

    # Validation
    assert df["fixed_stress_cost_usd"].ge(0).all()
    assert df["base_cost_usd"].ge(0).all()
    assert df["stress_cost_usd"].ge(0).all()

    df.to_csv(output_path, index=False)

    print("=== FIXED STRESS SCENARIO ===")
    print("Rows:", len(df))
    print("Output:", output_path)

    print(
        df[
            [
                "ticker",
                "base_cost_vol_points",
                "stress_cost_vol_points",
                "fixed_stress_cost_vol_points",
                "fixed_stress_cost_usd",
            ]
        ].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    main()
