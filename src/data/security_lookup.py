import pandas as pd

from .index_discovery import discover_optionmetrics_index


def sql_quote(value):
    """Quote a simple string value for use in SQL IN clauses."""
    value = str(value).replace("'", "''")
    return f"'{value}'"


def normalize_ticker(value):
    """Normalize a ticker-like identifier."""
    if value is None:
        return None

    value = str(value).upper().strip()
    return value or None


def ticker_variants(ticker):
    """
    Generate conservative ticker aliases.

    Example:
        AZN.2 -> ["AZN.2", "AZN"]
    """
    ticker = normalize_ticker(ticker)
    if ticker is None:
        return []

    variants = [ticker]
    if "." in ticker:
        base = ticker.split(".", 1)[0]
        if base:
            variants.append(base)

    return list(dict.fromkeys(variants))


def resolve_tickers_to_permnos(
    db,
    tickers,
    date,
    require_all=True,
):
    """Resolve contemporaneous CRSP tickers to PERMNOs."""
    date = pd.Timestamp(date).date()

    requested = [
        ticker
        for ticker in (normalize_ticker(x) for x in tickers)
        if ticker is not None
    ]
    requested = list(dict.fromkeys(requested))

    empty = pd.DataFrame(columns=["ticker", "permno"])
    if not requested:
        return empty

    ticker_sql = ",".join(sql_quote(x) for x in requested)

    df = db.raw_sql(
        f"""
        SELECT DISTINCT
            permno,
            ticker
        FROM crsp.dsf_v2
        WHERE dlycaldt = '{date}'
          AND UPPER(ticker) IN ({ticker_sql})
        """
    )

    if df.empty:
        if require_all:
            raise ValueError(
                f"No CRSP observations found for supplied tickers on {date}."
            )
        return empty

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    df = df.dropna(subset=["ticker", "permno"]).copy()
    df["permno"] = df["permno"].astype(int)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

    ambiguity = df.groupby("ticker")["permno"].nunique()
    ambiguous = ambiguity[ambiguity > 1].index.tolist()
    if ambiguous:
        raise ValueError(
            "Multiple PERMNOs found for ticker(s): " + ", ".join(ambiguous)
        )

    result = (
        df[["ticker", "permno"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    if require_all:
        missing = sorted(set(requested) - set(result["ticker"]))
        if missing:
            raise ValueError(
                "Ticker(s) not found in CRSP: " + ", ".join(missing)
            )

    return result


def resolve_compustat_tickers_to_permnos(
    db,
    constituent_tickers,
    date,
):
    """
    Resolve Compustat tickers to CRSP PERMNOs using exact ticker first,
    then conservative ticker aliases.
    """
    original_tickers = [
        ticker
        for ticker in (normalize_ticker(x) for x in constituent_tickers)
        if ticker is not None
    ]
    original_tickers = list(dict.fromkeys(original_tickers))

    all_variants = []
    for ticker in original_tickers:
        all_variants.extend(ticker_variants(ticker))
    all_variants = list(dict.fromkeys(all_variants))

    crsp = resolve_tickers_to_permnos(
        db=db,
        tickers=all_variants,
        date=date,
        require_all=False,
    )

    crsp_map = {
        row["ticker"]: int(row["permno"])
        for _, row in crsp.iterrows()
    }

    rows = []
    for original in original_tickers:
        matched_ticker = None
        permno = None

        for candidate in ticker_variants(original):
            if candidate in crsp_map:
                matched_ticker = candidate
                permno = crsp_map[candidate]
                break

        rows.append(
            {
                "compustat_ticker": original,
                "ticker": matched_ticker,
                "permno": permno,
            }
        )

    return pd.DataFrame(
        rows,
        columns=["compustat_ticker", "ticker", "permno"],
    )


def resolve_cusips_to_permnos(
    db,
    cusips,
    date,
):
    """
    Resolve CUSIPs through OptionMetrics and its historical CRSP link.
    Lower WRDS link scores are preferred.
    """
    date = pd.Timestamp(date).date()

    requested = [
        str(x).upper().strip()
        for x in cusips
        if pd.notna(x) and str(x).strip()
    ]
    requested = list(dict.fromkeys(requested))

    empty = pd.DataFrame(columns=["cusip", "permno"])
    if not requested:
        return empty

    cusip_sql = ",".join(sql_quote(x) for x in requested)

    df = db.raw_sql(
        f"""
        SELECT
            s.cusip,
            s.secid,
            l.permno,
            l.score,
            l.sdate,
            l.edate
        FROM optionm.securd s
        JOIN wrdsapps_link_crsp_optionm.opcrsphist l
          ON s.secid = l.secid
        WHERE UPPER(s.cusip) IN ({cusip_sql})
          AND l.permno IS NOT NULL
          AND (l.sdate IS NULL OR l.sdate <= '{date}')
          AND (l.edate IS NULL OR l.edate >= '{date}')
        """
    )

    if df.empty:
        return empty

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["secid"] = pd.to_numeric(df["secid"], errors="coerce")
    df = df.dropna(subset=["cusip", "permno"]).copy()
    df["permno"] = df["permno"].astype(int)
    df["cusip"] = df["cusip"].astype(str).str.upper().str.strip()
    df["score_sort"] = df["score"].fillna(999)
    df["secid_sort"] = df["secid"].fillna(float("inf"))

    result = (
        df.sort_values(["cusip", "score_sort", "secid_sort"])
        .drop_duplicates(subset=["cusip"], keep="first")
        [["cusip", "permno"]]
        .reset_index(drop=True)
    )
    return result


def attach_crsp_tickers(
    db,
    permnos,
    date,
):
    """Retrieve contemporaneous CRSP tickers for PERMNOs."""
    date = pd.Timestamp(date).date()
    permnos = [int(x) for x in permnos if pd.notna(x)]
    permnos = list(dict.fromkeys(permnos))

    empty = pd.DataFrame(columns=["ticker", "permno"])
    if not permnos:
        return empty

    permno_sql = ",".join(str(x) for x in permnos)

    df = db.raw_sql(
        f"""
        SELECT DISTINCT
            permno,
            ticker
        FROM crsp.dsf_v2
        WHERE dlycaldt = '{date}'
          AND permno IN ({permno_sql})
        """
    )

    if df.empty:
        return empty

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    df = df.dropna(subset=["permno", "ticker"]).copy()
    df["permno"] = df["permno"].astype(int)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

    ambiguity = df.groupby("permno")["ticker"].nunique()
    ambiguous = ambiguity[ambiguity > 1].index.tolist()
    if ambiguous:
        raise ValueError(
            "Multiple contemporaneous CRSP tickers found for PERMNO(s): "
            + ", ".join(str(x) for x in ambiguous)
        )

    return (
        df[["ticker", "permno"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def get_optionmetrics_secid(
    db,
    permno,
    ticker,
    date,
    days=30,
):
    """
    Map a CRSP PERMNO to its historical OptionMetrics SECID.

    Lower WRDS link score is preferred; tied distinct SECIDs are rejected.
    Option availability cannot establish security identity.
    """
    date = pd.Timestamp(date).date()
    ticker = normalize_ticker(ticker) or str(ticker)

    links = db.raw_sql(
        f"""
        SELECT
            secid,
            sdate,
            edate,
            permno,
            score
        FROM wrdsapps_link_crsp_optionm.opcrsphist
        WHERE permno = {int(permno)}
          AND (sdate IS NULL OR sdate <= '{date}')
          AND (edate IS NULL OR edate >= '{date}')
        ORDER BY score, secid
        """
    )

    if links.empty:
        raise ValueError(
            f"No PERMNO-SECID link found for {ticker} "
            f"(PERMNO {permno}) on {date}."
        )

    links["score"] = pd.to_numeric(links["score"], errors="coerce")
    links["secid"] = pd.to_numeric(links["secid"], errors="coerce")
    links = links.dropna(subset=["secid"]).copy()

    if links.empty:
        raise ValueError(f"No valid PERMNO-SECID links found for {ticker}.")

    from src.research.inputs import map_secid, normalize_table
    for column in ("sdate", "edate"):
        links[column] = pd.to_datetime(links[column])
    normalize_table("links", links)
    return map_secid(links, int(permno), pd.Timestamp(date))


def get_secid_from_ticker(db, ticker, date=None, days=30):
    """Historical ticker resolution; current metadata is insufficient for stock identity."""
    if date is None:
        raise ValueError("date is required for historical ticker resolution")
    try:
        return get_index_secid(db, ticker)
    except ValueError:
        matches = resolve_tickers_to_permnos(db, [ticker], date)
        if len(matches) != 1:
            raise ValueError("Ticker does not identify exactly one dated PERMNO")
        return get_optionmetrics_secid(db, int(matches.iloc[0].permno), ticker, date, days)


def get_index_secid(db, ticker):
    """Resolve an OptionMetrics index ticker to its SECID."""
    return int(
        discover_optionmetrics_index(
            db=db,
            ticker=ticker,
        )["secid"]
    )
