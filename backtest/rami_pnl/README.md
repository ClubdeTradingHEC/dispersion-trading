# Fichiers de P&L pour Mia : DJIA et S&P 500

Une ligne par trade, et le P&L quotidien de la stratégie, pour le Dow Jones (DJIA) en priorité et le S&P 500.
P&L en points de variance pour une unité de notionnel actions (× 10,3 $ pour des dollars). Chaque trade est
pris seul, à notionnel fixe : pas de capitalisation, pas de compensation entre trades qui se chevauchent.

## Fichiers

| Fichier | Contenu | Lignes | Période |
|---|---|---|---|
| `djia_1m_trades.csv` | DJIA, paris d'un mois : un trade par ligne | 334 | entrées du 1997-10-20 au 2025-07-21, dernière sortie 2025-08-15 |
| `djia_1m_strategy_daily.csv` | la stratégie, tous trades ouverts confondus, par jour | 6999 | idem |
| `sp500_3m_trades.csv` | S&P 500, paris de trois mois (le réglage réaliste) : un trade par ligne | 353 | entrées du 1996-01-22 au 2025-05-19, dernière sortie 2025-08-15 |
| `sp500_3m_strategy_daily.csv` | la stratégie, tous trades ouverts confondus, par jour | 7441 | idem |
| `sp500_1m_trades.csv` | S&P 500, paris d'un mois (même horizon que le DJIA) : un trade par ligne | 355 | entrées du 1996-01-22 au 2025-07-21, dernière sortie 2025-08-15 |
| `sp500_1m_strategy_daily.csv` | la stratégie, tous trades ouverts confondus, par jour | 7441 | idem |

## Colonnes

`*_trades.csv`

| Colonne | Sens |
|---|---|
| `entry` | date d'entrée : clôture du premier jour de bourse après l'échéance mensuelle (3e vendredi) |
| `exit` | date de sortie : l'échéance, le trade est tenu jusqu'au bout |
| `book` | mois de départ (0, 1 ou 2 pour les paris de 3 mois, qui se chevauchent ; toujours 0 à un mois) |
| `pnl_gross` | P&L brut, avant coûts |
| `pnl_net` | P&L net, après les coûts mesurés |

`*_strategy_daily.csv` : une ligne par jour de bourse.

| Colonne | Sens |
|---|---|
| `open_bets` | nombre de trades ouverts |
| `open_mark_gross`, `open_mark_net` | somme des valeurs estimées des trades ouverts |
| `pnl_day_gross`, `pnl_day_net` | P&L de la journée de la stratégie |
| `pnl_cum_gross`, `pnl_cum_net` | P&L cumulé depuis le début : trades clos à leur P&L réglé, trades ouverts à leur valeur estimée |

## Réglages

- **DJIA** : réglage C (vente de variance de l'indice dimensionnée en vega égal), tout le Dow à poids égaux
  (et non pondéré par le prix comme l'indice), paris d'un mois, prix de marché, coûts mesurés. Un mois parce que
  le prix de marché de la variance du Dow (VXD) n'existe qu'à 30 jours. Les options DJX ne commencent qu'à la fin
  de 1997 : les 21 premiers mois n'ont pas de trade, le premier entre le
  1997-10-20. Titres réellement cotés par trade : 27 à
  29 des 30.
- **S&P 500, 3 mois** : le réglage réaliste du projet (C, les 25 plus grandes capitalisations à poids égaux, prix de
  marché, coûts mesurés), identique à `outputs/09_entry_pnl/entry_pnl_realistic_sp500.csv`.
- **S&P 500, 1 mois** : le même réglage à un mois, pour comparer avec le DJIA.
- **Valeur quotidienne** (une estimation, pas un prix traité) : chaque jour, la variance réalisée depuis l'entrée
  pour les jours écoulés, plus la variance implicite du jour (prix de marché) pour les jours restants, moins le
  strike d'entrée ; poids, strikes et notionnel de l'indice fixés à l'entrée. La variance implicite des jours
  restants est interpolée entre les maturités 30, 60 et 91 jours de la surface (plate en dehors) ; une volatilité
  manquante reprend celle de la veille (par exemple du 27 juillet au 18 août 2020, où la surface OptionMetrics
  est vide). Le jour de l'échéance, la valeur est exactement le P&L réglé du trade (vérifié par un test). Fermer un
  trade avant l'échéance coûterait en plus l'écart acheteur-vendeur, qui n'est pas compté ici.

## Non inclus

- **L'écart MIV/IOIV** : le projet n'a pas cette série. Le code MIV du dépôt de l'équipe de Kevin en est la source.

## Limites

- **Prix de marché** : une constante, l'écart moyen entre l'indice de variance de Cboe et la volatilité put 25-delta,
  mesurée sur 2011-2025 et appliquée à toute la période, y compris 2008.
- **Coûts mesurés** : l'écart acheteur-vendeur coté d'options isolées (une par titre et par échéance), et non celui
  de toute la gamme de strikes qu'un vrai swap de variance demande.
- **Pas de coût de couverture** : la couverture delta quotidienne n'est pas facturée.

Analyse exploratoire des données, par Rami.
