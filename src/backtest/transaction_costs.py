
from dataclasses import dataclass


@dataclass
class FuturesCostConfig:
    # Example assumption, not a calibrated historical value.
    half_spread_ticks: float = 0.5
    tick_value_usd: float = 12.50
    commission_per_contract: float = 0.0


def option_execution_cost(
    quantity: float,
    base_cost_per_straddle: float,
    stress_cost_per_straddle: float,
    fixed_stress_cost_per_straddle: float,
    commission_per_straddle: float = 1.30,
    scenario: str = "base",
) -> float:
    """
    Cost of trading a quantity of straddles.

    All input costs are in USD per one-way execution,
    excluding commissions.
    """
    costs = {
        "base": base_cost_per_straddle,
        "stress": stress_cost_per_straddle,
        "fixed_stress": fixed_stress_cost_per_straddle,
    }

    if scenario not in costs:
        raise ValueError(f"Unknown scenario: {scenario}")

    if quantity == 0:
        return 0.0

    return abs(quantity) * (
        costs[scenario] + commission_per_straddle
    )


def stock_hedge_cost(
    shares_traded: float,
    half_spread_per_share: float,
    scenario: str = "base",
) -> float:
    """
    Bid/ask execution cost for the net number of shares traded.
    """
    multiplier = {
        "base": 1.0,
        "stress": 2.0,
        "fixed_stress": 1.0,
    }

    if scenario not in multiplier:
        raise ValueError(f"Unknown scenario: {scenario}")

    return (
        abs(shares_traded)
        * half_spread_per_share
        * multiplier[scenario]
    )


def futures_hedge_cost(
    contracts_traded: float,
    config: FuturesCostConfig,
) -> float:
    """
    Cost of trading futures, based on a configurable
    half-spread measured in ticks.
    """
    return abs(contracts_traded) * (
        config.half_spread_ticks * config.tick_value_usd
        + config.commission_per_contract
    )


def total_execution_cost(
    option_cost: float = 0.0,
    stock_cost: float = 0.0,
    futures_cost: float = 0.0,
) -> float:
    return option_cost + stock_cost + futures_cost
