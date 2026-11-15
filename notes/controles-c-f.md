# Contrôles C-F : ce qu'ils font (note de Joud, sam. 14 nov., décision #20)

En une phrase : chaque stratégie proposée passe automatiquement une **liste de 17 vérifications**, qui montre au
client (et au jury) qu'elle est diversifiée et adaptée à son profil, avec un chiffre et une raison pour chacune.
Code : `src/dh/agents/checks.py`. Seuils : `src/dh/agents/rules.py`. Tests : `tests/test_checks.py`.

## Le principe

Chaque contrôle répond toujours de la même façon :

> **quoi** (C2) · **valeur** (79 %) · **limite** (70 %) · **verdict** (✔ / ⚠ / ✘) · **raison en clair** · **source du chiffre**

- **✘ bloque** : la stratégie casse une contrainte du client et ne peut pas lui être proposée telle quelle.
- **⚠ informe** : c'est acceptable, mais on le dit au client.

## Les 17 contrôles, en clair

**C, la diversification : est-ce que les œufs sont dans plusieurs paniers ?**
- **C1** : aucune entreprise ne pèse trop lourd, *y compris ce qu'on en détient via les ETF*. Par exemple, 10 % de NVDA
  en direct + 50 % de QQQ, qui contient lui-même 9 % de NVDA, font en réalité 14,5 % de NVDA.
- **C2** : pas plus de 70 % des actions dans un seul pays (⚠). La raison affiche aussi la répartition CAD/USD.
- **C3** : pas un seul secteur au-dessus de 30 % (⚠) ni de 40 % (✘). C'est le test d'Amira : « pas que de la tech ».
- **C3b** : pas plus de 15 % dans **le secteur où travaille le client** (✘). S'il travaille dans l'énergie, une crise
  du secteur toucherait à la fois son salaire et son épargne.
- **C4** : au moins 2 classes d'actifs (actions, obligations, or, crypto).
- **C5** : assez de positions réelles, au moins 8 « effectives » en comptant l'intérieur des ETF (⚠).
- **C6** : pas deux fois le même pari. SPY et ESGV (corrélation 0,99) bloquent ; QQQ et SPY (0,95) sont signalés.

**D, le risque face au client : est-ce qu'il peut encaisser le pire ?**
- **D1** : la pire baisse passée comparée à ce que le client a dit pouvoir accepter (⚠ s'il en est proche).
- **D2** : la même chose **en dollars**, comparée à sa limite de perte (✘). Par exemple : « pire baisse 8,6 % =
  34 480 $, pour une limite de 60 000 $ ».
- **D3** : le comportement en 2022, la pire année glissante et les pires jours (CVaR).

**E, l'objectif :** la chance d'atteindre son montant cible, sans supposer que les rendements de 2021-2026 se répètent.

**F, l'adéquation au profil :**
- F1 objectif (un coussin de sécurité ne doit presque pas avoir d'actions) ;
- F2 horizon (respecte le plafond selon l'horizon, la décision #22) ;
- F3 liquidité (l'argent nécessaire dans 3 ans reste défensif) ;
- F4 niveau de connaissances (un débutant n'a que des ETF larges) ;
- F5 ESG (pas d'énergies fossiles si le client tient à l'ESG) ;
- F6 exclusions, en direct (✘) ou cachées dans un ETF (⚠).

## Où ça sert

1. **Dans le Portfolio :** chaque stratégie porte ses `checks`. S'il trouve un doublon (C6) ou un secteur trop lourd
   (C3), **il se corrige tout seul** (il fusionne le doublon ou transfère l'excédent vers un ETF large) et note ce qu'il
   a fait dans `adjustments`. Il annule la correction si elle cassait la limite de perte.
2. **Dans le Guardian :** 4 nouvelles règles, **G14 à G17** (géographie, secteur, concentration, perte en dollars).
   Elles appellent ces mêmes contrôles, donc il n'y a qu'une seule version de chaque règle.
3. **Pour la démo :** `python -m dh propose robert` affiche, par exemple :
   ```
   ## Income / dividends  14% growth / 86% defensive
      checks C-F: 16 ✔, 1 ⚠, 0 ✘ (C2 warn)
        ⚠ C2: Canada 79% of the equities; currency CAD 72%, USD 29%
   ```
4. **Pour les agents de Will :** l'Explainer peut citer n'importe quelle raison mot pour mot, et le Critic peut s'en
   servir comme outils.

## Résultat sur les personas (données 2021-2026)
- **Aucun ✘ :** toutes les stratégies proposées respectent les contraintes.
- **Les ⚠ disent quelque chose d'utile :** les stratégies « dividendes » sont très canadiennes (78-80 %) ; le Growth
  tilt d'Amira est 100 % américain, avec deux ETF presque identiques (QQQ/SPY 0,95), et sa pire baisse (−33 %) est
  proche de sa tolérance (40 %).

**Pourquoi c'est important pour le jury :** le brief exige que la solution « garde une logique de diversification et
sache expliquer ses choix ». Chaque contrôle est un chiffre vérifiable, avec sa raison et sa source.

**Limite à connaître :** on n'a le détail du contenu que pour un seul ETF (SPY), et sans secteur ni pays. Pour les
ETF, les contrôles secteur et pays sont donc des **bornes basses**, et le texte de chaque contrôle le précise.
Les seuils (70 %, 30 %/40 %, 15 %, 8, 0,85/0,95, 80 %) sont des hypothèses d'équipe (décision #20).
