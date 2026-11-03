"""
Tableau chiffré par type d'événement (FOMC, CPI, NFP) — S&P 500, août 2021 à juillet 2025.

Pour chaque événement au jour t (jour de bourse de l'annonce) :
    Δ1 = corr(t)   - corr(t-1)     -> effet du jour même
    Δ2 = corr(t+1) - corr(t-1)     -> jour même + lendemain
    Δ3 = corr(t+2) - corr(t-1)     -> 3 jours
corr = corrélation du panier (fenêtre 30 jours) calculée par basket_correlation_2021_2025.py.

Jours normaux : jours t sans FOMC, CPI ni NFP entre t-1 et t+2 (la fenêtre de mesure ne
contient aucun de ces événements). Même calcul de Δ1, Δ2, Δ3.

Test : différence de moyenne événement vs jours normaux (test de Welch) et test de
Mann-Whitney (ne suppose pas de loi normale). Petit échantillon : à lire avec prudence.

Tableau 2 : les mêmes Δ pour les jours de "mouvement large" du marché
(|rendement de l'indice| >= 1,5 % ET au moins 80 % des titres dans le même sens).

Entrées (même dossier) : basket_correlation_2021_2025.csv, macro_events.csv,
                         spx_returns_weights_2021_2025.csv
Sortie : event_study_2021_2025.xlsx (+ .csv)
Install : py -m pip install pandas numpy scipy openpyxl
"""
import numpy as np
import pandas as pd
from scipy import stats

CORR_FILE = "basket_correlation_2021_2025.csv"
EVENTS_FILE = "macro_events.csv"
DATA_FILE = "spx_returns_weights_2021_2025.csv"
OUT = "event_study_2021_2025"
TYPES = ["FOMC", "CPI", "NFP"]
BIG_MOVE = 0.015      # |rendement indice| >= 1,5 %
BREADTH = 0.80        # >= 80 % des titres dans le même sens que l'indice

# ---------------------------------------------------------------- données
corr = pd.read_csv(CORR_FILE, parse_dates=["date"]).set_index("date")["rc_basket"]
days = corr.index
pos = pd.Series(np.arange(len(days)), index=days)

ev = pd.read_csv(EVENTS_FILE, parse_dates=["trading_date"])
ev = ev[ev["event_type"].isin(TYPES) & ev["trading_date"].isin(days)]
ev = ev.drop_duplicates(["trading_date", "event_type"])


def deltas(i):
    """Δ1, Δ2, Δ3 pour le jour à la position i (NaN si hors de la série)."""
    if i - 1 < 0 or i + 2 >= len(days):
        return [np.nan] * 3
    base = corr.iloc[i - 1]
    return [corr.iloc[i] - base, corr.iloc[i + 1] - base, corr.iloc[i + 2] - base]


all_d = pd.DataFrame([deltas(i) for i in range(len(days))], index=days, columns=["d1", "d2", "d3"])

# jours normaux : aucun FOMC/CPI/NFP entre t-1 et t+2
event_pos = set(pos[ev["trading_date"]].tolist())
normal_mask = [not any(j in event_pos for j in range(i - 1, i + 3)) for i in range(len(days))]
normal = all_d[normal_mask].dropna()

# mouvements larges du marché
raw = pd.read_csv(DATA_FILE, parse_dates=["date"])
raw["wr"] = raw["weight"] * raw["daily_return"]
idx_ret = raw.groupby("date")["wr"].sum()
raw = raw.join(idx_ret.rename("idx"), on="date")
same = (np.sign(raw["daily_return"]) == np.sign(raw["idx"])) & raw["daily_return"].notna()
breadth = same.groupby(raw["date"]).mean()
mkt = pd.DataFrame({"index_return": idx_ret, "breadth": breadth}).reindex(days)
mkt["broad_move"] = (mkt["index_return"].abs() >= BIG_MOVE) & (mkt["breadth"] >= BREADTH)


def summarize(name, d, n_label=None):
    row = {"Groupe": name, "N": len(d)}
    for k, lab in [("d1", "1 jour"), ("d2", "2 jours"), ("d3", "3 jours")]:
        x = d[k].dropna()
        row[f"Δ moyen {lab}"] = x.mean()
        if name != "Jours normaux":
            row[f"p-value {lab} (Welch)"] = stats.ttest_ind(x, normal[k], equal_var=False).pvalue
    x3 = d["d3"].dropna()
    row["Médiane Δ 3 jours"] = x3.median()
    row["% hausses (3 jours)"] = (x3 > 0).mean()
    row["|Δ| moyen 3 jours"] = x3.abs().mean()
    if name != "Jours normaux":
        row["p-value |Δ| 3 jours (Mann-Whitney)"] = stats.mannwhitneyu(
            x3.abs(), normal["d3"].abs(), alternative="two-sided").pvalue
    return row


rows = [summarize("Jours normaux", normal)]
for t in TYPES:
    p = pos[ev.loc[ev["event_type"] == t, "trading_date"]].tolist()
    rows.append(summarize(t, all_d.iloc[p].dropna()))
table1 = pd.DataFrame(rows)

# Tableau 2 : mouvement large vs non, événement vs non
is_event = pd.Series(False, index=days)
is_event.iloc[list(event_pos)] = True
groups = {
    "Mouvement large, jour FOMC/CPI/NFP": mkt["broad_move"] & is_event,
    "Mouvement large, autre jour": mkt["broad_move"] & ~is_event,
    "FOMC/CPI/NFP sans mouvement large": ~mkt["broad_move"] & is_event,
}
rows2 = [summarize("Jours normaux", normal)]
for name, m in groups.items():
    rows2.append(summarize(name, all_d[m.values].dropna()))
table2 = pd.DataFrame(rows2)

# Détail événement par événement
detail = ev[["trading_date", "event_type"]].copy()
detail[["d1", "d2", "d3"]] = all_d.loc[detail["trading_date"]].values
detail = detail.join(mkt, on="trading_date").sort_values("trading_date")

# ---------------------------------------------------------------- sortie
pd.set_option("display.width", 200)
print(table1.round(3).to_string(index=False))
print()
print(table2.round(3).to_string(index=False))
table1.to_csv(f"{OUT}.csv", index=False)
with pd.ExcelWriter(f"{OUT}.xlsx", engine="openpyxl") as xw:
    table1.to_excel(xw, index=False, sheet_name="par type")
    table2.to_excel(xw, index=False, sheet_name="mouvements larges")
    out_d = detail.copy()
    out_d["trading_date"] = out_d["trading_date"].dt.date
    out_d.to_excel(xw, index=False, sheet_name="détail")
    for ws in xw.sheets.values():
        ws.freeze_panes = "B2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 16
print(f"\nSaved {OUT}.xlsx and {OUT}.csv")
