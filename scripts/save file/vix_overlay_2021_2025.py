"""
Point 4 — VIX sur les graphiques de corrélation (S&P 500, août 2021 à juillet 2025).

Deux types de graphiques, pour toute la période, 2022 et le printemps 2025 :
  1) vix_corr_*.png : corrélation du panier (axe de gauche) + VIX (axe de droite).
  2) vix_rv_*.png   : VIX du jour t vs volatilité réalisée de l'indice sur les 21 jours de
                      bourse suivants (t+1 à t+21), annualisée. Zone rouge = la volatilité
                      réalisée a dépassé le VIX -> une vente de volatilité de l'indice au
                      niveau du VIX ce jour-là aurait perdu (avant coûts).

Attention : le VIX est une volatilité implicite de l'indice, pas une corrélation implicite.
Il mesure seulement la jambe "indice" de la stratégie. À remplacer par la corrélation
implicite quand on l'aura.

Entrées (même dossier) : basket_correlation_2021_2025.csv, VIXCLS.csv (FRED),
                         spx_returns_weights_2021_2025.csv, macro_events.csv (optionnel)
Sorties : 6 images PNG + vix_overlay_2021_2025.csv
Install : py -m pip install pandas numpy matplotlib
"""
import os
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CORR_FILE = "basket_correlation_2021_2025.csv"
VIX_FILE = "VIXCLS.csv"
DATA_FILE = "spx_returns_weights_2021_2025.csv"
EVENTS_FILE = "macro_events.csv"
HORIZON = 21                     # jours de bourse (~ 30 jours de calendrier, comme le VIX)

PERIODS = {                      # nom de fichier -> (début, fin, titre)
    "full": (None, None, "août 2021 à juillet 2025"),
    "2022": ("2022-01-01", "2022-12-31", "2022"),
    "2025_spring": ("2025-03-01", "2025-05-31", "mars à mai 2025"),
}
SHOCK_TITLES = {                 # titres courts pour les zooms (date de réaction du marché)
    "2022-02-24": "Ukraine", "2022-03-08": "Russian oil ban",
    "2025-04-03": "Liberation Day", "2025-04-09": "Tariff pause", "2025-05-12": "Geneva deal",
}
C_CORR, C_VIX, C_RV, C_LOSS, C_SHOCK = "#1f4e79", "#e4572e", "#5b6770", "#e4572e", "#2a9d4b"

# Même taille de cadre que les autres graphiques : 25,20 cm x 7,25 cm
GRAPH_W_CM, GRAPH_H_CM, CM = 25.20, 7.25, 1 / 2.54


def make_axes(rotated_ticks):
    aw, ah = GRAPH_W_CM * CM, GRAPH_H_CM * CM
    left, right, top, bottom = 0.8, 0.8, 0.45, 2.0
    fw, fh = left + aw + right, bottom + ah + top
    fig = plt.figure(figsize=(fw, fh))
    ax = fig.add_axes((left / fw, bottom / fh, aw / fw, ah / fh))
    return fig, ax, -(0.62 if rotated_ticks else 0.32) / ah


def save(fig, name):
    try:
        fig.savefig(name, dpi=150, bbox_inches="tight", pad_inches=0.12)
        print(f"Saved {name}")
    except OSError:
        print(f"!! Impossible d'écrire {name} : ferme ce fichier s'il est ouvert, puis relance.")
    plt.close(fig)


# ---------------------------------------------------------------- données
corr = pd.read_csv(CORR_FILE, parse_dates=["date"]).set_index("date")["rc_basket"]
vix = pd.read_csv(VIX_FILE, parse_dates=["observation_date"]).set_index("observation_date")["VIXCLS"]
raw = pd.read_csv(DATA_FILE, parse_dates=["date"])
idx = (raw["weight"] * raw["daily_return"]).groupby(raw["date"]).sum()
# volatilité réalisée des 21 jours SUIVANTS (t+1 ... t+21), en % annualisé
fwd_rv = idx[::-1].rolling(HORIZON).std()[::-1].shift(-1) * np.sqrt(252) * 100

df = pd.DataFrame({"rc_basket": corr, "vix": vix.reindex(corr.index).ffill(),
                   "fwd_realized_vol": fwd_rv.reindex(corr.index)})
df["realized_above_vix"] = (df["fwd_realized_vol"] > df["vix"]).astype(float)
df.loc[df["fwd_realized_vol"].isna(), "realized_above_vix"] = np.nan   # pas encore 21 jours après

shocks = []
if os.path.exists(EVENTS_FILE):
    ev = pd.read_csv(EVENTS_FILE, parse_dates=["trading_date"])
    shocks = sorted(set(ev.loc[ev["event_type"] == "SHOCK", "trading_date"]))


def draw_shocks(ax, d):
    """Lignes verticales pour les chocs du zoom, étiquettes sur 2 rangs pour éviter le chevauchement."""
    in_range = [s for s in shocks if d.index.min() <= s <= d.index.max()
                and s.strftime("%Y-%m-%d") in SHOCK_TITLES]
    for k, s in enumerate(in_range):
        ax.axvline(s, color=C_SHOCK, lw=0.9, ls="--", alpha=0.8, zorder=1)
        ax.annotate(f"{SHOCK_TITLES[s.strftime('%Y-%m-%d')]} · {s:%d %b}", (s, 1 - 0.07 * (k % 2) - 0.02),
                    xycoords=("data", "axes fraction"), ha="left", va="top", fontsize=7.5,
                    color=C_SHOCK, fontweight="bold", xytext=(3, 0), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=C_SHOCK, lw=0.5))


# ---------------------------------------------------------------- graphiques
for key, (a, b, label) in PERIODS.items():
    d = df.loc[a:b]
    zoom = key != "full"

    # 1) corrélation + VIX
    fig, ax, legend_y = make_axes(rotated_ticks=(key == "2025_spring"))
    l1, = ax.plot(d.index, d["rc_basket"], color=C_CORR, lw=1.8, label="Corrélation du panier (axe gauche)")
    ax.set_ylabel("Corrélation", color=C_CORR)
    ax2 = ax.twinx()
    l2, = ax2.plot(d.index, d["vix"], color=C_VIX, lw=1.2, label="VIX (axe droit)")
    ax2.set_ylabel("VIX", color=C_VIX)
    ax.grid(alpha=0.3)
    ax.set_title(f"S&P 500 — corrélation du panier et VIX, {label}")
    if zoom:
        draw_shocks(ax, d)
        ax.xaxis.set_major_locator(mdates.MonthLocator() if key == "2022" else mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b" if key == "2022" else "%d %b"))
        if key != "2022":
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend([l1, l2], [l1.get_label(), l2.get_label()], loc="upper center",
              bbox_to_anchor=(0.5, legend_y), ncol=2, fontsize=8.5, frameon=False)
    save(fig, f"vix_corr_{key}.png")

    # 2) VIX vs volatilité réalisée des 21 jours suivants
    fig, ax, legend_y = make_axes(rotated_ticks=(key == "2025_spring"))
    dv = d.dropna(subset=["fwd_realized_vol"])
    ax.plot(dv.index, dv["vix"], color=C_VIX, lw=1.4, label="VIX au jour t (volatilité implicite)")
    ax.plot(dv.index, dv["fwd_realized_vol"], color=C_RV, lw=1.4,
            label="Volatilité réalisée de l'indice, 21 jours suivants")
    ax.fill_between(dv.index, dv["vix"], dv["fwd_realized_vol"], where=dv["fwd_realized_vol"] > dv["vix"],
                    color=C_LOSS, alpha=0.25, interpolate=True, label="Réalisée > VIX (vente de volatilité perdante)")
    ax.set_ylabel("Volatilité annualisée (%)")
    ax.grid(alpha=0.3)
    ax.set_title(f"S&P 500 — VIX vs volatilité réalisée des 21 jours suivants, {label}")
    if zoom:
        draw_shocks(ax, d)
        ax.xaxis.set_major_locator(mdates.MonthLocator() if key == "2022" else mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b" if key == "2022" else "%d %b"))
        if key != "2022":
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, legend_y), ncol=3, fontsize=8.5, frameon=False)
    save(fig, f"vix_rv_{key}.png")

# ---------------------------------------------------------------- résumé chiffré
v = df.dropna(subset=["fwd_realized_vol"])
print(f"\nCorrélation entre la corrélation du panier et le VIX : {df['rc_basket'].corr(df['vix']):.2f}")
print("Part des jours où la volatilité réalisée des 21 jours suivants a dépassé le VIX :")
for y, g in v.groupby(v.index.year):
    print(f"  {y}: {g['realized_above_vix'].mean():.0%}  (VIX moyen {g['vix'].mean():.1f}, "
          f"réalisée moyenne {g['fwd_realized_vol'].mean():.1f}, corrélation moyenne {g['rc_basket'].mean():.2f})")
print(f"  Total : {v['realized_above_vix'].mean():.0%} des {len(v)} jours")

out = df.copy()
out.index = out.index.date
out.to_csv("vix_overlay_2021_2025.csv", index_label="date")
print("Saved vix_overlay_2021_2025.csv")
