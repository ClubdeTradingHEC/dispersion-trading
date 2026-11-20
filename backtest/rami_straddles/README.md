# La dispersion avec des straddles couverts (tâche 2)

Le même trade que les swaps de variance (acheter la volatilité des grandes actions, vendre celle de l'indice), mais
avec un straddle (un call et un put) couvert en delta chaque jour, par titre : acheté sur les actions, vendu sur le
S&P 500. Un straddle couvert gagne quand le prix bouge plus que l'option ne le suppose ; il vise donc la même prime
que le swap, mais son gain dépend aussi du chemin : une fois le prix loin du prix d'exercice, il réagit moins.

P&L en points de variance pour une unité de notionnel actions (× 10,3 $ pour des dollars), comme les fichiers de
`backtest/rami_pnl/`. Un nouveau pari à chaque entrée mensuelle (355 entrées, de janvier 1996 à juillet 2025),
chaque pari pris seul à notionnel fixe. Les statistiques sont calculées sur ces paris mensuels.

## Fichiers

| Fichier | Contenu |
|---|---|
| `straddle_grid_scorecard.csv` | les 15 mesures standard du projet pour chaque case de la grille, sur tout l'échantillon, depuis 2012 et par cinquième de l'échantillon, avant coûts et dans les scénarios base et stress de Kevin, avec et sans commission (210 lignes) |
| `straddle_grid_legs.png` | gain moyen par pari de chaque jambe (actions, indice) par cinquième de l'échantillon, pour les six cases, avant coûts |
| `straddle_cost_parts.png` | top 10 au scénario base : ce que coûte un pari en moyenne, par cinquième, partie par partie |
| `straddle_gap_pieces.png` | top 10 : l'écart moyen entre le straddle et le swap, par cinquième, découpé en trois morceaux |

Colonnes du `.csv` : `N` (taille du panier), `holding` (`expiry` : tenu jusqu'à l'échéance ; `10 days` : revendu après 10
jours de bourse), `period`, `costs` (`before costs`, `base`, `stress`), `commission` (`yes`/`no`), `bets`, puis les 15
mesures : `ic` (corrélation entre l'avantage mesuré à l'entrée et le P&L), `hit_rate` (part des paris gagnants),
`sharpe`, `information_ratio`, `expectancy`, `profit_factor`, `win_loss_ratio`, `cagr`, `skew`, `kurtosis`,
`pnl_concentration` (part du P&L venant des 5 % plus gros paris), `max_drawdown`, `avg_drawdown`, `turnover`,
`breakeven_bp` (coût d'équilibre en points de vol par jambe). Les rendements sont ramenés à 10 % de volatilité par an
avant de calculer les mesures en pourcentage.

## Ce que fait le simulateur

| Étape | Ce qui est fait |
|---|---|
| Entrée | clôture du jour d'entrée (les mêmes dates que les swaps) ; prime du call +50 delta et du put −50 delta à 30 jours, sur la surface de volatilité OptionMetrics |
| Durée | l'option vit 30 jours calendaires (environ 21 jours de bourse) |
| Taille | vega neutre à l'entrée : le même vega acheté sur les actions et vendu sur l'indice |
| Valeur quotidienne | Black-Scholes au prix du jour, mêmes strikes, vol à la monnaie du jour, sans smile |
| Couverture | chaque jour, on neutralise le delta : les actions avec leurs titres, l'indice avec son niveau (pour un SPY ou un future) |
| Sortie | à l'échéance, la valeur intrinsèque ; pour la version 10 jours, revente au prix Black-Scholes du 10e jour de bourse |
| Coûts | les définitions de Kevin, refaites depuis les cotations pour chaque date depuis 1996 (ses fichiers couvrent 2019) |

La grille, fixée d'avance : top 10, 20 ou 30 actions du S&P 500 × tenu jusqu'à l'échéance ou revendu après 10 jours,
soit six cases. Rien n'a été ajusté dessus.

## Les deux validations demandées

| Test | Corrélation | Lecture |
|---|---|---|
| AAPL seul, contre (variance réalisée − variance implicite) × vega, 355 entrées | 0,68 | 0,84 en rangs. Un monde simulé sans problème de données donne environ 0,85. Sans couverture, le test tombe à 0,31 : il détecte une erreur. |
| Contre le simulateur de swaps, top 10, tenu à l'échéance, mêmes dates et mêmes paniers | 0,59 | 0,72 en rangs |
| Idem, depuis 2012 | 0,26 | un seul pari, entré en février 2020, fait la baisse : 0,66 sans lui. Cet effet vient de l'instrument, pas d'un défaut. |
| Idem, revendu après 10 jours | 0,83 | |

Tenu à l'échéance, le straddle gagne en moyenne 10,1 points de moins par pari que le swap (t de −0,70). Cet écart
faible cache deux écarts opposés sur les jambes : −99,1 sur les actions et +89,0 sur l'indice. On ne peut donc pas
en conclure que le straddle coûte peu par rapport au swap. `straddle_gap_pieces.png` découpe l'écart en trois
morceaux : le calendrier (30 jours fixes contre le cycle mensuel), la répartition (vega contre variance par poids)
et l'instrument lui-même.

## La grille, avant coûts

Gain moyen par pari (points de variance) et ratio de Sharpe :

| Case | Tout l'échantillon | Sharpe | Depuis 2012 | Sharpe depuis 2012 |
|---|---|---|---|---|
| top 10, tenu à l'échéance | +49,4 | 0,69 | −10,1 | −0,18 |
| top 10, revendu après 10 jours | +24,0 | 0,47 | +10,1 | 0,20 |
| top 20, tenu à l'échéance | +62,3 | 0,89 | +3,0 | 0,06 |
| top 20, revendu après 10 jours | +29,3 | 0,64 | +11,5 | 0,27 |
| top 30, tenu à l'échéance | +69,9 | 1,01 | +5,9 | 0,13 |
| top 30, revendu après 10 jours | +30,5 | 0,69 | +9,4 | 0,25 |

Tenu à l'échéance, c'est la jambe indice qui porte le résultat en moyenne (top 30 : +85,9 par pari, contre −16,1
pour les actions) ; `straddle_grid_legs.png` le montre par période.

## Après les coûts de Kevin

Par exécution : **base**, la moitié de l'écart acheteur-vendeur du straddle coté et la demi-fourchette sur chaque
action échangée pour la couverture ; **stress**, l'écart entier et le double sur les actions. Plus 0,65 $ par contrat.
La couverture de l'indice par le future S&P 500 coûte un demi-tick, une hypothèse non calibrée (c'est ainsi que le
module de Kevin la décrit). Un pari tenu à l'échéance ne paie pas d'écart à la sortie.

Gain moyen par pari après coûts, commission comprise (Sharpe entre parenthèses) :

| Case | Avant coûts | Base | Stress | Base depuis 2012 | Stress depuis 2012 |
|---|---|---|---|---|---|
| top 10, tenu à l'échéance | +49,4 (0,69) | −109,1 (−1,33) | −255,7 (−2,04) | −64,3 (−0,99) | −112,7 (−1,42) |
| top 10, revendu après 10 jours | +24,0 (0,47) | −160,1 (−2,29) | −332,0 (−3,03) | −75,0 (−1,18) | −154,2 (−1,82) |
| top 20, tenu à l'échéance | +62,3 (0,89) | −115,1 (−1,39) | −279,9 (−2,07) | −53,4 (−0,87) | −103,6 (−1,29) |
| top 20, revendu après 10 jours | +29,3 (0,64) | −171,4 (−2,48) | −358,7 (−3,08) | −78,0 (−1,28) | −160,7 (−1,79) |
| top 30, tenu à l'échéance | +69,9 (1,01) | −119,6 (−1,39) | −296,2 (−2,03) | −54,3 (−0,84) | −108,1 (−1,20) |
| top 30, revendu après 10 jours | +30,5 (0,69) | −181,0 (−2,51) | −378,4 (−3,04) | −85,7 (−1,31) | −173,4 (−1,71) |

**Le gain moyen après coûts est négatif dans les six cases et les deux scénarios, sur tout l'échantillon comme depuis
2012.** Au scénario base, le top 10 tenu à l'échéance paie en moyenne par pari : couverture des actions 76,1 ; options
sur actions 43,4 ; options sur l'indice 27,2 ; future S&P 500 7,3 (hypothèse) ; commissions 4,5. Ce coût passe de 442
par pari dans le premier cinquième de l'échantillon à 67 dans le dernier (`straddle_cost_parts.png`).

**Le scénario « stress fixe » (4,09 points de vol par exécution) n'est plus montré.** Kevin l'a retiré de son modèle
de coûts le 16 novembre : 4,09 est désormais un seuil d'entrée optionnel (|IOIV − MIV| ≥ 4,09 points), appliqué une
fois par signal, et non un coût par exécution. Ces chiffres gardent ses scénarios base et stress, qui n'ont pas changé.

## Limites

- **La grille est à 30 jours** : elle paie ses coûts environ 12 fois par an et se couvre chaque jour. Ces chiffres ne
  disent rien de direct sur le réglage en swaps à 3 mois. Un horizon de 3 mois, étiqueté à part, est la prochaine étape
  décidée.
- **Un point de la surface, pas un contrat coté** : le straddle à 30 jours et à la monnaie est standardisé ; aucun vrai
  straddle coté n'a été tenu sur sa durée. Son coût est celui du contrat coté le plus proche, appliqué à ce point.
- **Pas de smile, pas d'exercice anticipé** : une seule vol à la monnaie pour les deux options, et une valeur
  européenne. Les cases à 10 jours achètent au prix de la surface (qui reflète des options américaines) et revendent
  à une formule européenne, ce qui les sous-estime d'environ 6 à 8 points par pari ; le signe de leur gain depuis 2012
  dépend de la règle de maturité de la vol. Une valeur américaine à la sortie, du même modèle qu'à l'entrée, est la
  correction décidée.
- **Prix de remplacement** : quand la sélection de Kevin ne trouve pas de straddle coté, un autre prix le remplace ;
  cela concerne 25 % du vega des actions à l'entrée sur tout l'échantillon, 4 % depuis 2012.
- **Options hebdomadaires** : la sélection de Kevin (l'échéance la plus proche de 30 jours) prend des hebdomadaires,
  plus chères à traiter, à partir de 2014. Sur échéances standard, le top 10 au scénario base depuis 2014 passe de
  −69,0 à −54,9 par pari.
- **La commission** suppose une taille de portefeuille et des contrats fractionnés.
- **Les fichiers de 2019 de Kevin** n'ont pas encore été comparés à cette reconstruction.
- **Paniers** : la correction de l'ancien Viacom (compté comme une seule société) n'est pas reportée ici ; elle
  changerait le top 30 sur 18 dates d'entrée de 2000 à 2004.

## Non inclus

Le P&L par date d'entrée et par jambe, le nuage de points de la validation AAPL et les courbes pari par pari : ils
permettraient de remonter à des données sous licence (volatilités implicites et cotations OptionMetrics). Ce dossier
ne contient que des résultats agrégés.

Analyse exploratoire des données, par Rami.
