INDEX_CONFIG = {
    "DJIA": {
        "benchmark": "DJX",
        "weighting": "price",
        "membership_source": "csv",
    },

    "SPX": {
        "benchmark": "SPX",
        "weighting": "market_cap",
        "membership_source": "crsp_sp500",
    },
}


ALIASES = {
    "DJI": "DJIA",
    "DOW": "DJIA",
    "DJX": "DJIA",

    "SP500": "SPX",
    "S&P500": "SPX",
    "S&P 500": "SPX",
}


def normalize_index(index: str) -> str:
    index = index.upper().strip()
    return ALIASES.get(index, index)


def get_index_config(index: str) -> dict:
    index = normalize_index(index)

    if index not in INDEX_CONFIG:
        raise ValueError(
            f"Index '{index}' is not configured. "
            f"Available indices: {', '.join(INDEX_CONFIG.keys())}"
        )

    return INDEX_CONFIG[index]