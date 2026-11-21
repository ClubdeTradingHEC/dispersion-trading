# Le cadre d'optimisation des signaux (tâche 3)

Avant de toucher au moindre seuil d'un signal d'entrée, ce cadre fixe les règles : quelles années servent à choisir,
quelles années vérifient le choix, quelles années restent intactes jusqu'à la fin, comment les seuils s'écrivent,
quels seuils ont le droit d'être essayés, et comment on compte les essais. Il a été écrit avant tout code de seuil. Il
ne règle rien et ne choisit aucun seuil : vos signaux viennent ensuite.

Il s'applique par défaut au réglage réaliste du projet sur le S&P 500 (les paris de `backtest/rami_pnl/sp500_3m_trades.csv` :
réglage C, top 25 à poids égaux, paris de 3 mois, prix de marché, coûts mesurés).

## Les trois périodes

| Période | Entrées du | au | Sert à | Paris du réglage |
|---|---|---|---|---|
| **Optimisation** | 1996-01-01 | 2012-12-31 | choisir une combinaison par signal | 201 |
| **Validation** | 2013-01-01 | 2018-12-31 | vérifier cette seule combinaison | 69 |
| **Réservée** | 2019-01-01 | 2025-08-29 (fin des données) | une seule fois, à la fin | 77 |

Un pari appartient à la période de sa date d'entrée, **à condition de se terminer dans la même période**. Un pari à
cheval sur deux périodes est retiré des deux et compté : 6 paris de 3 mois (les trois dernières entrées de chacune
des deux premières périodes). Ainsi, aucun pari d'une période ne lit les rendements de la suivante.

**Deux limites à connaître.**
- La période réservée n'est pas vierge pour tout : des analyses antérieures ont déjà regardé 2019-2025 pour ce
  réglage. Elle reste propre seulement pour des signaux et des seuils pas encore regardés.
- Le prix de chaque pari contient une information postérieure : le « prix de marché » ajoute une constante mesurée
  sur 2011-2025, et le coût mesuré se rabat sur une médiane de tout l'échantillon les jours sans cotation. Retirer les
  paris à cheval sépare les périodes ; cela ne rend pas les prix datés.

## Un signal, et des seuils relatifs calculés sur le passé seulement

Un signal arrive comme un fichier CSV à deux colonnes, `date,value` (voir `exemple_signal.csv`). Chaque entrée prend
la dernière valeur datée au plus tard de son jour d'entrée. **Une valeur datée du jour $D$ doit être connue à la
clôture de $D$**, délai de publication compris : le code ne peut pas le vérifier, c'est à l'auteur du signal de le
garantir.

La valeur est ensuite comparée aux seules entrées précédentes. Avec $W_t$ les entrées précédentes de la fenêtre
(l'entrée du jour exclue) :

$$p_t=\frac{\#\{s\in W_t:x_s<x_t\}+\tfrac12\#\{s\in W_t:x_s=x_t\}}{|W_t|},\qquad
z_t=\frac{x_t-\bar x_{W_t}}{\mathrm{sd}(x_{W_t})}.$$

- **Passé seulement** : changer une valeur plus récente ne change jamais $p_t$ ni $z_t$ (vérifié par un test).
- **Rodage** : avec moins de 36 valeurs précédentes, pas de valeur transformée ; l'entrée est sautée et comptée. Un
  signal qui commence en 1996 a donc sa première valeur vers 1999.
- Les périodes ne remettent pas l'historique à zéro : une entrée de validation se compare aussi aux entrées de la
  période d'optimisation. Les valeurs postérieures à la fin d'une période sont retirées avant le calcul.

## La grille, décidée d'avance

Chaque signal reçoit la même grille, comme filtre d'entrée (on entre quand la valeur transformée passe le seuil ; une
entrée sautée ne rapporte rien) :

| Choix | Valeurs | Nombre |
|---|---|---|
| Transformation | percentile $p_t$, score z $z_t$ | 2 |
| Fenêtre | les 36 entrées précédentes, ou toutes les entrées précédentes (au moins 36) | 2 |
| Seuil | percentile 0,25, 0,50, 0,75 ; score z −1, 0, +1 | 3 |
| Sens | entrer au-dessus du seuil (ou égal), ou en dessous (ou égal) | 2 |

Soit **24 combinaisons par signal et par réglage.** Les deux sens sont dans la grille, parce que le cadre ne présume
pas ce que veut dire un signal. Changer quoi que ce soit ici demande une décision écrite avant le calcul, et les
essais déjà comptés restent comptés.

## Ce que fait chaque période

1. **Optimisation.** Les 24 combinaisons tournent. On retient celle qui a le meilleur ratio de Sharpe après coûts
   mesurés parmi celles qui ont tradé au moins 30 entrées. Si aucune n'y arrive, le signal s'arrête là.
2. **Validation.** Cette seule combinaison tourne sur les 69 paris de validation. Elle passe si les paris où elle
   entre, après coûts, font mieux qu'au moins 95 % de 10 000 tirages au hasard d'autant de paris parmi les mêmes
   entrées (graine fixe). La comparaison porte sur le Sharpe par pari : moyenne sur écart-type du P&L net des paris
   gardés. Seules les entrées où le signal a une valeur sont tirées, donc un signal qui commence tard n'est pas comparé
   à des années qu'il n'a jamais vues. Avec moins de 5 paris gardés, ou si toutes les entrées sont gardées, il n'y a
   rien à juger et la vérification échoue. Le résultat donne la part des tirages battus, pour qu'un échec de peu se
   voie. Aucune autre combinaison n'est essayée ici : ce serait transformer la validation en optimisation.
3. **Réservée.** Quand chaque signal est passé par les deux premières étapes, les survivants tournent ensemble, une
   seule fois. Le code refuse cette période sans une option explicite et une raison, et il enregistre chaque usage ;
   un second usage est enregistré aussi et se voit dans le compte.

**La règle de validation a changé le 10 novembre, avant tout vrai signal.** La première version comparait le Sharpe du
signal, une entrée sautée comptant pour zéro, à celui du trade sans signal. L'audit interne a montré qu'elle rejette
un signal parfait : un signal construit exprès, qui entre sur 35 des 69 paris de validation et les gagne tous,
obtenait 1,784 contre 1,898 sans signal, parce que trader moitié moins d'entrées baisse ce Sharpe même quand chaque
pari gardé gagne. La règle de tirages ci-dessus compare à périmètre égal : le même signal parfait bat maintenant 100 %
des tirages, et du pur bruit passe environ 5 % du temps (3,8 % sur 600 essais). Aucun résultat n'est touché, car aucun
vrai signal n'avait été lancé.

## Comment on compte les essais

Un registre en ajout seul garde une ligne par combinaison lancée, chaque ligne contenant l'empreinte de la précédente,
pour qu'une modification ou une suppression se voie. Une combinaison, c'est : le nom du signal, l'empreinte de son
fichier, le réglage, la transformation, la fenêtre, le seuil, le sens et la période. Une grille complète sur
l'optimisation en ajoute 24, la validation 1. Un fichier de signal révisé a une nouvelle empreinte : ses combinaisons
sont nouvelles. Le compte ne repart jamais à zéro : il est cumulé sur toute l'équipe et tous les signaux, et toute
correction pour tests multiples l'utilise. Aujourd'hui : **0 combinaison**, aucun signal n'a encore été essayé.

## Le trade sans signal, pour comparer

Le réglage par défaut, sans signal, après coûts mesurés (paris retirés exclus) :

| Période | Paris | P&L brut moyen par pari | P&L net moyen par pari | Sharpe par pari (moyenne / écart-type) | Ratio de Sharpe annuel |
|---|---|---|---|---|---|
| Optimisation 1996-2012 | 201 | 206,2 | 120,9 | 0,32 | 0,64 |
| Validation 2013-2018 | 69 | 78,4 | 58,8 | 0,95 | 1,90 |

La période réservée est laissée de côté exprès.

## Proposer un signal

1. Un fichier `date,value` : en-tête exactement `date,value`, dates `AAAA-MM-JJ`, une valeur numérique finie par ligne,
   pas de date en double, dans n'importe quel ordre. Les fichiers qui ne respectent pas ce format sont refusés, avec le
   numéro des lignes en cause.
2. Chaque valeur datée du jour où elle est connue.
3. Envoyez-le-moi ; je le passe dans la grille d'optimisation, puis la combinaison retenue en validation, et le compte
   de combinaisons est mis à jour. La période réservée attend que tous les signaux soient passés.

`exemple_signal.csv` montre le format : des nombres au hasard entre 0 et 1 (graine fixe), un par fin de mois depuis
1998. Il ne contient aucune information et n'est pas compté.

## Ce qui reste à faire

- La sélection sur l'optimisation (le meilleur Sharpe avec au moins 30 entrées) favorise encore les filtres qui
  tradent souvent : c'est la règle demandée, elle reste.
- Le registre vit dans git : deux personnes qui ajoutent en même temps casseraient sa chaîne, donc une seule à la fois.
- La batterie de robustesse (intervalles par bootstrap, tests appariés, corrections pour tests multiples, placebos)
  reste à côté du cadre. Sur l'historique complet d'un signal, elle regarde la période réservée : elle passe donc après
  le passage du signal sur la période réservée.

Analyse exploratoire des données, par Rami.
