"""
Build a CSV/Excel of macro event dates with descriptions.
- FRED releases (CPI, NFP, GDP, PCE, PPI, Retail Sales, JOLTS): actual release dates
- FOMC: decision dates (statement day = 2nd day of meeting), incl. 2020 emergency moves
- SHOCK: hand-curated list of major unscheduled market events
Columns: date | event_type | description | trading_date
  trading_date = first weekday on/after the event (weekend events -> Monday;
  US market holidays are not adjusted)
Install (in PowerShell): py -m pip install requests pandas openpyxl
"""
import requests
import pandas as pd

API_KEY = "YOUR_FRED_API_KEY"   # mets ta clé ici (ne pas la pousser sur GitHub)
START = "2015-01-01"
END = pd.Timestamp.today().strftime("%Y-%m-%d")   # only dates that already happened
BASE = "https://api.stlouisfed.org/fred"

# label -> exact FRED release name
FRED_RELEASES = {
    "CPI": "Consumer Price Index",
    "NFP": "Employment Situation",
    "GDP": "Gross Domestic Product",
    "PCE": "Personal Income and Outlays",
    "PPI": "Producer Price Index",
    "RETAIL": "Advance Monthly Sales for Retail and Food Services",
    "JOLTS": "Job Openings and Labor Turnover Survey",
}
# CPI/PPI publish seasonal-factor revisions a few days BEFORE the main release -> keep last
KEEP_LAST = {"CPI", "PPI"}   # all others: keep first date in the month

DESCRIPTIONS = {
    "CPI": "US consumer inflation (CPI), BLS, 8:30 ET",
    "NFP": "US jobs report (nonfarm payrolls, unemployment rate), BLS, 8:30 ET",
    "GDP": "US GDP estimate (advance/second/third), BEA, 8:30 ET",
    "PCE": "Personal income & spending, PCE inflation (Fed's preferred gauge), BEA, 8:30 ET",
    "PPI": "US producer prices (PPI), BLS, 8:30 ET",
    "RETAIL": "US retail sales, Census Bureau, 8:30 ET",
    "JOLTS": "US job openings and labor turnover (JOLTS), BLS, 10:00 ET",
    "FOMC": "FOMC interest rate decision and statement, 14:00 ET",
}

# FOMC decision dates. Verify against:
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES = [
    "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17", "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
    "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15", "2016-07-27", "2016-09-21", "2016-11-02", "2016-12-14",
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14", "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
FOMC_SPECIAL = {
    "2020-03-03": "EMERGENCY FOMC: 50 bp cut (COVID), unscheduled",
    "2020-03-15": "EMERGENCY FOMC (Sunday): cut to 0-0.25% + QE (COVID), unscheduled",
}

# Major unscheduled shocks. 2021-2025 dates verified against press sources (Nov 2026).
# AFTER_CLOSE: announced after the 16:00 ET close -> the market reacts the next trading day.
SHOCKS = [
    ("2015-08-11", "China devalues the yuan; global selloff begins"),
    ("2015-08-24", "'Black Monday' flash crash; Dow opens ~1,000 pts down"),
    ("2016-06-24", "Brexit referendum result (vote held June 23)"),
    ("2016-11-09", "Trump wins 2016 US presidential election (vote Nov 8)"),
    ("2018-02-05", "'Volmageddon': VIX spike, short-vol products collapse"),
    ("2018-03-22", "Trump announces Section 301 tariffs on China; trade war starts"),
    ("2019-05-05", "Trump threatens tariff hike on China (Sunday); trade war escalates"),
    ("2019-08-05", "Yuan breaks 7/USD; US labels China a currency manipulator"),
    ("2020-02-24", "COVID crash begins (outbreak spreads in Italy)"),
    ("2020-03-09", "Saudi-Russia oil price war; oil -25%, first circuit breaker"),
    ("2020-03-16", "COVID crash: Dow -2,997 pts, circuit breaker"),
    ("2020-04-20", "WTI oil futures settle negative for the first time"),
    ("2020-11-09", "Pfizer announces effective COVID vaccine; rotation rally"),
    ("2021-01-27", "GameStop / meme-stock short squeeze peak"),
    ("2022-02-24", "Russia invades Ukraine"),
    ("2022-03-08", "US bans Russian oil imports; Brent near $128"),
    ("2023-03-10", "Silicon Valley Bank fails; regional bank crisis"),
    ("2023-03-19", "UBS takeover of Credit Suisse (Sunday)"),
    ("2023-08-01", "Fitch downgrades US credit rating from AAA (announced after close)"),
    ("2023-10-07", "Hamas attack on Israel (Saturday); Middle East war"),
    ("2024-08-05", "Yen carry-trade unwind; VIX spikes intraday above 60"),
    ("2024-11-06", "Trump wins 2024 US presidential election (vote Nov 5)"),
    ("2025-01-27", "DeepSeek AI shock; Nvidia -17%, tech selloff"),
    ("2025-02-01", "Trump signs tariffs on Canada, Mexico, China (Saturday)"),
    ("2025-04-02", "'Liberation Day' reciprocal tariffs (announced after close)"),
    ("2025-04-09", "Trump announces 90-day tariff pause; huge rally"),
    ("2025-05-12", "US-China Geneva deal: tariffs cut for 90 days"),
    ("2025-06-13", "Israel strikes Iran; oil jumps"),
    ("2025-06-21", "US strikes Iranian nuclear sites (Saturday)"),
    ("2025-10-01", "US federal government shutdown begins; data releases delayed"),
    ("2025-11-12", "US government shutdown ends"),
]
AFTER_CLOSE = {"2023-08-01", "2025-04-02"}


def get(endpoint, **params):
    params.update(api_key=API_KEY, file_type="json")
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# 1) Look up FRED release IDs by name
releases, offset = [], 0
while True:
    page = get("releases", limit=1000, offset=offset)
    releases += page["releases"]
    offset += 1000
    if offset >= page["count"]:
        break
name_to_id = {r["name"]: r["id"] for r in releases}

ids = {}
for label, name in FRED_RELEASES.items():
    if name in name_to_id:
        ids[label] = name_to_id[name]
    else:
        word = name.split()[0].lower()
        close = [n for n in name_to_id if word in n.lower()][:10]
        print(f"'{name}' not found for {label}. Similar names on FRED: {close}")
print("Release IDs:", ids)

# 2) Collect all events
rows = []
for label, rid in ids.items():
    data = get("release/dates", release_id=rid,
               realtime_start=START, realtime_end="9999-12-31",
               include_release_dates_with_no_data="false",
               limit=10000, sort_order="asc")
    for d in data["release_dates"]:
        rows.append({"date": d["date"], "event_type": label,
                     "description": DESCRIPTIONS[label]})
for d in FOMC_DATES:
    rows.append({"date": d, "event_type": "FOMC",
                 "description": FOMC_SPECIAL.get(d, DESCRIPTIONS["FOMC"])})
for d, desc in SHOCKS:
    rows.append({"date": d, "event_type": "SHOCK", "description": desc})

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = (df[(df["date"] >= START) & (df["date"] <= END)]
      .drop_duplicates().sort_values("date").reset_index(drop=True))

# 3) Keep one date per month for each FRED release (removes revisions/reissues)
parts = [df[df["event_type"].isin(["FOMC", "SHOCK"])]]
for label in ids:
    sub = df[df["event_type"] == label]
    g = sub.groupby(sub["date"].dt.to_period("M"))
    kept = g.tail(1) if label in KEEP_LAST else g.head(1)
    dropped = sub.drop(kept.index)
    if not dropped.empty:
        print(f"\n{label}: removed {len(dropped)} extra date(s):",
              ", ".join(dropped["date"].dt.strftime("%Y-%m-%d")))
    parts.append(kept)
df = pd.concat(parts).sort_values(["date", "event_type"]).reset_index(drop=True)

# 4) Trading date: weekend events roll to Monday
df["trading_date"] = df["date"].apply(pd.offsets.BDay().rollforward)
after = (df["event_type"] == "SHOCK") & df["date"].dt.strftime("%Y-%m-%d").isin(AFTER_CLOSE)
df.loc[after, "trading_date"] = df.loc[after, "date"] + pd.offsets.BDay(1)

print("\nCounts per year:")
print(df.groupby([df["date"].dt.year, "event_type"]).size().unstack(fill_value=0))

out = df.copy()
out["date"] = out["date"].dt.date
out["trading_date"] = out["trading_date"].dt.date
out.to_csv("macro_events.csv", index=False)
with pd.ExcelWriter("macro_events.xlsx", engine="openpyxl") as xw:
    out.to_excel(xw, index=False, sheet_name="events")
    ws = xw.sheets["events"]
    for col, width in zip("ABCD", [12, 11, 75, 13]):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
print("\nSaved macro_events.csv and macro_events.xlsx")
