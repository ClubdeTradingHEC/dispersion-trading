import pandas as pd


def get_stock_prices(
    db,
    constituents=None,
    permnos=None,
    tickers=None,
    date=None,
):
    """
    Pull CRSP stock data used for index weighting.

    Selection priority:
        constituents -> PERMNOs/tickers
        explicit PERMNOs
        explicit tickers
    """
    if date is None:
        raise ValueError("date is required.")

    if constituents is not None:
        if "permno" in constituents.columns:
            permnos = (
                constituents["permno"]
                .dropna()
                .astype(int)
                .unique()
                .tolist()
            )
        elif "ticker" in constituents.columns:
            tickers = (
                constituents["ticker"]
                .dropna()
                .astype(str)
                .str.upper()
                .str.strip()
                .unique()
                .tolist()
            )

    if permnos:
        values = ",".join(str(int(x)) for x in permnos)
        where_clause = f"permno IN ({values})"
    elif tickers:
        normalized = [str(x).upper().strip().replace("'", "''") for x in tickers]
        values = ",".join(f"'{x}'" for x in normalized)
        where_clause = f"UPPER(ticker) IN ({values})"
    else:
        raise ValueError("Provide constituents, permnos, or tickers.")

    df = db.raw_sql(
        f"""
        SELECT
            permno,
            ticker,
            ABS(dlyprc) AS price,
            dlycap
        FROM crsp.dsf_v2
        WHERE dlycaldt = '{pd.Timestamp(date).date()}'
          AND {where_clause}
        """
    )

    if df.empty:
        return df

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["dlycap"] = pd.to_numeric(df["dlycap"], errors="coerce")
    df = df.dropna(subset=["permno", "ticker"]).copy()
    df["permno"] = df["permno"].astype(int)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

    # A PERMNO should identify one contemporaneous security row for the date.
    df = df.drop_duplicates(subset=["permno"]).reset_index(drop=True)
    return df


def _normalize_weights(stocks, value_column, missing_message):
    stocks = stocks.dropna(subset=[value_column]).copy()
    if stocks.empty:
        raise ValueError(missing_message)

    total = float(stocks[value_column].sum())
    if total <= 0:
        raise ValueError(f"Total {value_column} must be positive.")

    stocks["weight"] = stocks[value_column] / total
    return stocks


def compute_price_weights(db, constituents, date):
    """Price weighting: w_i = P_i / sum(P_j)."""
    stocks = get_stock_prices(db=db, constituents=constituents, date=date)
    if stocks.empty:
        raise ValueError("No constituent prices found.")
    return _normalize_weights(stocks, "price", "All constituent prices are missing.")


def compute_market_cap_weights(db, constituents, date):
    """Raw market-cap proxy weighting using CRSP dlycap."""
    stocks = get_stock_prices(db=db, constituents=constituents, date=date)
    if stocks.empty:
        raise ValueError("No constituent stock data found.")
    return _normalize_weights(
        stocks,
        "dlycap",
        "All constituent market caps are missing.",
    )


def compute_equal_weights(db, constituents, date):
    """Equal weighting: w_i = 1/N."""
    stocks = get_stock_prices(db=db, constituents=constituents, date=date)
    if stocks.empty:
        raise ValueError("No constituent stock data found.")

    stocks = stocks.copy()
    stocks["weight"] = 1.0 / len(stocks)
    return stocks


def get_index_weights(db, constituents, date, method):
    """Dispatch to price, market-cap, or equal weighting."""
    method = str(method).lower().strip()

    functions = {
        "price": compute_price_weights,
        "market_cap": compute_market_cap_weights,
        "equal": compute_equal_weights,
    }

    if method not in functions:
        raise ValueError(f"Unsupported weighting method: {method}")

    return functions[method](
        db=db,
        constituents=constituents,
        date=date,
    )


def compute_djia_weights(prices):
    """Backward-compatible normalized price weighting helper."""
    if prices.empty:
        raise ValueError("No prices provided.")

    prices = prices.copy()
    prices["price"] = pd.to_numeric(prices["price"], errors="coerce")
    return _normalize_weights(prices, "price", "All prices are missing.")
