"""
Étape 3 (v2) — Corrélation du panier (S&P 500), jour par jour, avec TOUS les événements.

Même calcul que basket_correlation.py :
  RC_panier(t) = Σ_{i≠j} a_ij · ρ_ij      a_ij = w_i·w_j / Σ_{k≠l} w_k·w_l
  ρ_ij = corrélation des rendements quotidiens sur les 30 derniers jours (t inclus)
  Raccourci : Σ_{i≠j} w_i w_j ρ_ij = w'Rw − Σ w_i²

Nouveautés de la v2 :
  - tous les types d'événements de macro_events.csv sont dessinés, chacun avec sa
    couleur et sa forme (légende sous le graphique)
  - étiquettes seulement pour FOMC et les chocs (les chocs avec leur titre)
  - chocs 2024 supplémentaires (EXTRA_SHOCKS ci-dessous)
  - tous les fichiers de sortie ont un nouveau nom (suffixe _v2) : rien n'est écrasé

Entrée  : spx_returns_weights_2024.csv, macro_events.csv (même dossier)
Sortie  : basket_correlation_v2.csv / .xlsx
          basket_correlation_v2.png (année) + basket_correlation_v2_Q1_2024.png ... Q4
Install : py -m pip install pandas numpy openpyxl matplotlib
"""
import os
import numpy as np
import pandas as pd

DATA_FILE = "spx_returns_weights_2024.csv"
EVENTS_FILE = "macro_events.csv"
OUT = "basket_correlation_v2"     # préfixe des fichiers de sortie
WINDOW = 30
MIN_OBS = WINDOW

# Chocs ajoutés à la main (date du jour J ; un week-end est reporté au lundi).
# Le titre court est celui qui s'affiche sur le graphique.
EXTRA_SHOCKS = [
    ("2024-03-19", "BoJ ends negative rates",       "Bank of Japan ends negative interest rates"),
    ("2024-04-13", "Iran attacks Israel",           "Iran attacks Israel with drones and missiles (Saturday)"),
    ("2024-07-13", "Trump assassination attempt",   "Assassination attempt on Trump (Saturday)"),
    ("2024-07-19", "CrowdStrike IT outage",         "Global CrowdStrike IT outage"),
    ("2024-07-21", "Biden withdraws",               "Biden withdraws from the presidential race (Sunday)"),
]
# Titres courts pour les chocs déjà présents dans macro_events.csv (sinon : début de la description)
SHOCK_TITLES = {
    "2024-08-05": "Yen carry-trade unwind",
    "2024-11-06": "Trump wins election",
}

# Style de chaque type d'événement : couleur, forme du point, nom dans la légende.
# FOMC et SHOCK ont en plus une étiquette sur le graphique ; les autres sont
# identifiés seulement par la légende.
STYLES = {
    "SHOCK":  ("#2a9d4b", "D", "Choc majeur"),
    "FOMC":   ("#e4572e", "o", "FOMC (décision de taux)"),
    "CPI":    ("#7b3fa0", "s", "CPI (inflation)"),
    "PPI":    ("#c05ab8", "p", "PPI (prix producteurs)"),
    "PCE":    ("#4a2c8a", "h", "PCE (inflation, Fed)"),
    "NFP":    ("#1f8fb3", "^", "NFP (rapport emploi)"),
    "JOLTS":  ("#5bb8d6", "<", "JOLTS (postes vacants)"),
    "GDP":    ("#b07a12", "v", "GDP (PIB)"),
    "RETAIL": ("#d4a017", ">", "Retail Sales (ventes au détail)"),
}
LABELLED = ("SHOCK", "FOMC")
LINE_COLOR, EQUAL_COLOR = "#1f4e79", "#9aa5b1"

# ---------------------------------------------------------------------------
# 1) Corrélation du panier
# ---------------------------------------------------------------------------
raw = pd.read_csv(DATA_FILE, parse_dates=["date"])
ret = raw.pivot(index="date", columns="permno", values="daily_return").sort_index()
wgt = raw.pivot(index="date", columns="permno", values="weight").sort_index()
dates = ret.index

results = []
for t in range(WINDOW - 1, len(dates)):
    day = dates[t]
    window = ret.iloc[t - WINDOW + 1: t + 1]
    in_index = wgt.loc[day].dropna().index
    stocks = in_index.intersection(window.columns[window.notna().sum() >= MIN_OBS])

    w = wgt.loc[day, stocks].to_numpy()
    w = w / w.sum()
    R = np.corrcoef(window[stocks].to_numpy(), rowvar=False)
    n = len(stocks)
    results.append({"date": day,
                    "rc_basket": (w @ R @ w - np.sum(w ** 2)) / (1.0 - np.sum(w ** 2)),
                    "rc_equal_weight": (R.sum() - n) / (n * (n - 1)),
                    "n_stocks": n, "n_excluded": len(in_index) - n})
out = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# 2) Événements : macro_events.csv + chocs supplémentaires
# ---------------------------------------------------------------------------
if os.path.exists(EVENTS_FILE):
    ev = pd.read_csv(EVENTS_FILE, parse_dates=["date", "trading_date"])
else:
    print(f"({EVENTS_FILE} introuvable : seuls les chocs supplémentaires seront affichés)")
    ev = pd.DataFrame(columns=["date", "event_type", "description", "trading_date"])

extra = pd.DataFrame([{"date": pd.Timestamp(d), "event_type": "SHOCK",
                       "description": desc, "title": title}
                      for d, title, desc in EXTRA_SHOCKS])
extra["trading_date"] = extra["date"].apply(pd.offsets.BDay().rollforward)
ev = pd.concat([ev, extra], ignore_index=True)
ev = ev.drop_duplicates(["date", "event_type"], keep="first")   # pas de doublon si déjà dans le fichier

def short_title(row):
    if row["event_type"] != "SHOCK":
        return row["event_type"]
    if isinstance(row.get("title"), str):
        return row["title"]
    d = row["date"].strftime("%Y-%m-%d")
    return SHOCK_TITLES.get(d, str(row["description"]).split(";")[0][:32])

ev["label"] = ev.apply(short_title, axis=1)
ev = ev[ev["event_type"].isin(STYLES)]

per_day = (ev.groupby("trading_date")
             .agg(events=("event_type", lambda s: ", ".join(sorted(set(s)))),
                  event_description=("description", lambda s: " | ".join(map(str, s))))
             .reset_index().rename(columns={"trading_date": "date"}))
out = out.merge(per_day, on="date", how="left")

# ---------------------------------------------------------------------------
# 3) Sauvegarde des chiffres
# ---------------------------------------------------------------------------
print(out[["rc_basket", "rc_equal_weight", "n_stocks"]].describe().round(3))
save = out.copy()
save["date"] = save["date"].dt.date
save.to_csv(f"{OUT}.csv", index=False)
with pd.ExcelWriter(f"{OUT}.xlsx", engine="openpyxl") as xw:
    save.to_excel(xw, index=False, sheet_name="rc_basket")
    ws = xw.sheets["rc_basket"]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, width in zip("ABCDEFG", [12, 11, 16, 10, 11, 24, 90]):
        ws.column_dimensions[col].width = width
print(f"\nSaved {OUT}.csv and {OUT}.xlsx")

# ---------------------------------------------------------------------------
# 4) Graphiques
# ---------------------------------------------------------------------------
# Taille de la zone du graphique (le cadre avec les courbes), en centimètres.
# L'image PNG est un peu plus grande : elle ajoute le titre, les axes et la légende.
GRAPH_W_CM, GRAPH_H_CM = 25.20, 7.25
CM = 1 / 2.54


def make_axes(rotated_ticks):
    """Figure dont le cadre du graphique mesure exactement GRAPH_W_CM x GRAPH_H_CM."""
    import matplotlib.pyplot as plt
    aw, ah = GRAPH_W_CM * CM, GRAPH_H_CM * CM            # en pouces
    left, right, top, bottom = 0.8, 0.3, 0.45, 2.0        # marges larges, recadrées à l'enregistrement
    fw, fh = left + aw + right, bottom + ah + top
    fig = plt.figure(figsize=(fw, fh))
    ax = fig.add_axes((left / fw, bottom / fh, aw / fw, ah / fh))
    tick_room = 0.62 if rotated_ticks else 0.32           # place prise par les dates sous l'axe (pouces)
    return fig, ax, -tick_room / ah                       # position de la légende (fraction de l'axe)



def _overlaps(box, others, pad=3):
    return any(box.x0 - pad < o.x1 and box.x1 + pad > o.x0 and
               box.y0 - pad < o.y1 and box.y1 + pad > o.y0 for o in others)


def build_labels(data):
    """Une étiquette par jour, seulement pour FOMC et les chocs (titre du choc)."""
    labels = []
    curve = data.set_index("date")["rc_basket"]
    sub = ev[ev["trading_date"].isin(curve.index) & ev["event_type"].isin(LABELLED)]
    for day, grp in sub.groupby("trading_date"):
        shocks = grp[grp["event_type"] == "SHOCK"]
        parts = list(shocks["label"]) + (["FOMC"] if (grp["event_type"] == "FOMC").any() else [])
        color = STYLES["SHOCK" if not shocks.empty else "FOMC"][0]
        labels.append((day, curve[day], f"{' + '.join(parts)} · {day:%d %b}", color))
    return labels


def draw(data, title, filename, figsize, size, weekly_ticks):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, ax, legend_y = make_axes(rotated_ticks=weekly_ticks)
    ax.plot(data["date"], data["rc_basket"], lw=1.8, color=LINE_COLOR,
            label="Corrélation du panier (pondérée)", zorder=2)
    ax.plot(data["date"], data["rc_equal_weight"], lw=1, color=EQUAL_COLOR,
            label="Moyenne simple des paires", zorder=2)

    # points : les types sans étiquette d'abord, FOMC et chocs par-dessus
    curve = data.set_index("date")["rc_basket"]
    for typ in ["RETAIL", "GDP", "JOLTS", "NFP", "PCE", "PPI", "CPI", "FOMC", "SHOCK"]:
        color, marker, name = STYLES[typ]
        days = sorted(set(ev.loc[ev["event_type"] == typ, "trading_date"]) & set(curve.index))
        if not days:
            continue
        if typ in LABELLED:
            for d in days:
                ax.axvline(d, color=color, alpha=0.15, lw=1, zorder=1)
        ax.scatter(days, curve[days], s=size * (1.2 if typ in LABELLED else 1), marker=marker,
                   color=color, edgecolor="white", linewidth=0.9,
                   zorder=4 if typ in LABELLED else 3, label=name)

    ax.set_title(title)
    ax.set_ylabel("Corrélation")
    ax.grid(alpha=0.3)
    if weekly_ticks:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        fig.autofmt_xdate()

    handles, names = ax.get_legend_handles_labels()
    ax.legend(handles, names, loc="upper center", bbox_to_anchor=(0.5, legend_y),
              ncol=min(len(names), 4), fontsize=8, frameon=False)

    lo = min(data["rc_basket"].min(), data["rc_equal_weight"].min())
    hi = max(data["rc_basket"].max(), data["rc_equal_weight"].max())
    span = hi - lo
    ax.set_ylim(lo - 0.08 * span, hi + 0.08 * span)

    labels = build_labels(data)
    if labels:
        # Étiquettes dans une bande en haut ; si elle touche une autre, elle descend d'un rang.
        renderer = fig.canvas.get_renderer()
        ax_h = ax.get_window_extent(renderer).height
        TOP = 0.97
        x0, x1 = ax.get_xlim()
        boxes, leaders, lowest = [], [], TOP
        for d, y, text, color in sorted(labels):
            frac = (mdates.date2num(d) - x0) / (x1 - x0)
            ha = "left" if frac < 0.08 else "right" if frac > 0.92 else "center"
            ypos = TOP
            while True:
                ann = ax.annotate(text, xy=(d, y), xytext=(d, ypos),
                                  textcoords=("data", "axes fraction"), ha=ha, va="top",
                                  fontsize=7, color=color, fontweight="bold", zorder=6,
                                  bbox=dict(boxstyle="round,pad=0.22", fc="white",
                                            ec=color, lw=0.6))
                box = ann.get_window_extent(renderer)
                if not _overlaps(box, boxes):
                    break
                ann.remove()
                ypos -= (box.height + 4) / ax_h              # un rang plus bas
            boxes.append(box)
            leaders.append((d, y, color, box))
            lowest = min(lowest, ax.transAxes.inverted().transform((0, box.y0))[1])

        # les courbes doivent rester sous la plus basse étiquette
        band_bottom = lowest - 0.03
        bottom = lo - 0.08 * span
        ax.set_ylim(bottom, bottom + (hi - bottom) / band_bottom)

        to_axes = ax.transAxes.inverted()
        for d, y, color, box in leaders:
            yb = to_axes.transform(((box.x0 + box.x1) / 2, box.y0))[1]
            ax.annotate("", xy=(d, y), xytext=(d, yb), textcoords=("data", "axes fraction"),
                        zorder=2.5, arrowprops=dict(arrowstyle="-", color=color, lw=0.7,
                                                    linestyle=(0, (2, 2)), shrinkA=0, shrinkB=4))
    try:
        fig.savefig(filename, dpi=150, bbox_inches="tight", pad_inches=0.12)
        print(f"Saved {filename}")
    except OSError:
        print(f"!! Impossible d'écrire {filename} : ferme ce fichier s'il est ouvert, puis relance.")
    plt.close(fig)


try:
    import matplotlib  # noqa: F401
    # Année complète
    draw(out, f"S&P 500 — corrélation du panier, fenêtre {WINDOW} jours",
         f"{OUT}.png", None, size=30, weekly_ticks=False)
    # Trimestres
    out["quarter"] = out["date"].dt.to_period("Q")
    for q, data in out.groupby("quarter"):
        draw(data, f"S&P 500 — corrélation du panier, {q.year} T{q.quarter} (fenêtre {WINDOW} jours)",
             f"{OUT}_Q{q.quarter}_{q.year}.png", None, size=40, weekly_ticks=True)
except ImportError:
    print("(matplotlib non installé : pas de graphique)")
