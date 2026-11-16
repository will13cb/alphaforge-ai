# AlphaForge AI — Documentation technique

William Caron-Bastarache · Joud Katbe · Datathon PolyFinances 2026 (Banque Nationale × AWS). Les sections suivent
l'énoncé (p. 15). Simulation seulement, profils fictifs, pas un conseil financier.
Application : https://alphaforge-ai-wj.streamlit.app/ · Dépôt : https://github.com/will13cb/alphaforge-ai

> Chaque nombre cité pour les personas figure dans `results.csv` (expériences `persona-*`, `standin-*`,
> `guardian-scenarios`). Les décisions citées #n sont dans `notes/decisions.md` (notes de l'équipe, en anglais).

## 1. Agents, rôles et contrôles

**Logique d'ensemble** (graphe : `aws/architecture.png`). `src/dh/agents/pipeline.py` exécute les agents dans un ordre
fixe, avec une seule ronde du Critique. Chacun lit et écrit de simples dictionnaires JSON (`notes/contract.md`), et
chaque relais est inscrit dans une trace. L'ordre est fixe exprès : un agent décide *à l'intérieur* de son étape (quels
outils appeler, à quoi objecter, comment le dire), jamais de l'étape suivante, pour que le Gardien ne puisse pas être
contourné (#14). Quatre étapes sont des **agents Strands sur Amazon Bedrock** (Claude Opus 5.5) : ils choisissent les
outils déterministes à appeler. Tout ce qui fixe une limite ou un nombre est du Python ordinaire. *Les agents
enquêtent et argumentent; le code fait respecter.*

| Étape | Agent | Fonctionnement | Résultat |
|---|---|---|---|
| 0 | **Extracteur** (`extractor.py`) | agent Strands, outil `check_profile` | les champs du profil à partir des mots du client; chaque nombre doit figurer dans son texte; éléments essentiels manquants → questions (#29) |
| 1 | **Profileur** (`profiler.py`) | règles | tolérance et capacité de risque, score de connaissances; limite de perte (% et $); plancher défensif; un plafond par société et pour la crypto; chacun avec sa raison écrite; signale les demandes qui ne conviennent pas; choix KYC en contre-vérification (#40) |
| 2 | **Données de marché** (`market.py`, Joud) | déterministe | par actif : rendement, volatilité, pire baisse, CVaR 95 %, pires 12 mois, 2022; corrélations; perspective d'objectif |
| 3 | **Portefeuille** (`portfolio.py`, `checks.py`) | règles + données | jusqu'à 3 stratégies avec leur répartition, leurs statistiques, les contrôles de diversification C–F et la note de chaque ajustement |
| — | **Gardien** (`guardian.py`) | règles de perte, de diversification et de cohérence | ✔ / ⚠ / ✘ après le Profileur, après chaque stratégie, après le texte |
| 4 | **Critique** (`critic.py`) | agent Strands, 11 outils, ≤ 6 appels | ≤ 3 objections, chacune appuyée par un résultat d'outil obtenu; une correction par stratégie, recalculée par le code (#30) |
| — | **Demande côte à côte** (`requests.py`) | règles | la demande du client « telle que demandée » et « ce qui convient », mêmes contrôles; avantages et inconvénients tirés des nombres seulement (#28) |
| 5 | **Explicateur** (`explainer.py`) | agent Strands, outil `check_text` | le texte au client, écrit à partir de faits où chaque nombre est un identifiant (#23, #27) |
| app | **Analyste** (`analyst.py`) | agent Strands, outils, ≤ 5 appels | réponses aux questions de suivi; ses scénarios relancent tout le pipeline (#35) |
| app | **Portefeuille déjà détenu** (`existing.py`) | règles + les mêmes agents | ce que le client détient déjà, revu avec les mêmes contrôles C–F et le Gardien, puis reconstruit vers la première stratégie proposée, chaque mouvement en $ (#42, #44) |
| app | **Recherche d'obligations** (`agents/fixed_income.py`) | règles, sans LLM | pour une préférence « obligations seulement » : titres gouvernementaux canadiens et américains sourcés, détenus jusqu'à l'échéance (taux, échéance, flux en CAD), ou « aucune correspondance appuyée »; références publiques, pas des offres de courtiers; ne promet jamais un taux garanti qu'elle ne peut sourcer |
| — | **Stockage des traces** (`tracestore.py`) | Amazon S3 | toute l'exécution en JSON dans `s3://<compartiment>/traces/`, depuis les deux applications et la ligne de commande (#25) |

**Ce que fait un ✘.** Sur le profil (G1) : aucune proposition, on interroge le client. Sur une stratégie : elle est
retirée et la trace dit quelle règle. Sur une correction du Critique : la stratégie d'origine est conservée. Sur le
texte : le gabarit déterministe le remplace. Rien ne revient en boucle (le Critique a une seule ronde) : chaque
exécution se termine, et la trace dit ce qui s'est passé.

**Contrôles (Gardien).** Des contrôles de convenance *calqués sur* les obligations canadiennes de connaissance du
client et de convenance (Règlement 31-103, art. 13.2–13.3); pas un test de conformité juridique (#3).
- **Avant toute proposition :** G1, les faits essentiels doivent être connus; sinon, on interroge le client.
- **Sur chaque stratégie :**
  - G2 pondérations valides; G3 actifs permis seulement; G4 chaque société sous son propre plafond, comptée à travers
    les FNB; G5 crypto;
  - G6 plancher défensif; G7 règle de perte : probabilité simulée d'une baisse plus forte que la limite de perte du
    client sur son horizon ≤ 10 %, sur les pondérations finales (#46); G8 volatilité (avertissement);
  - G9 une demande qui ne convient pas n'est jamais appliquée en douce; G10 exclusions détenues à travers des FNB
    (divulguées);
  - G14–G16 (de `checks.py`, #20) : géographie, secteur et secteur d'emploi du client, concentration (la pire baisse
    en $ fait maintenant partie de G7);
  - G18 cohérence : chaque nombre affiché décrit les pondérations et les données finales (#46). 17 règles en tout.
- **Sur le texte :** G11 l'avertissement est présent; G12 chaque % et chaque $ est exactement un des faits calculés;
  G13 chaque demande qui ne convient pas est expliquée.

**Ce que chaque agent peut faire, et ce que le code vérifie.**
- **Extracteur :** remplit seulement les champs que le client a mentionnés. Le code vérifie le schéma, associe les noms
  aux symboles (Tesla → TSLA) et retire tout nombre qui n'est pas écrit dans le texte du client; ce qui manque est
  demandé, jamais deviné (#29).
- **Critique :** choisit ce qui semble douteux et enquête avec des outils avant d'objecter : les outils de marché de
  Joud (`portfolio_stats`, `stress_test`, `correlation_between`, `goal_check`, `required_return`…), des vues sur
  l'exécution (`look_through`, `strategy_checks`, `limit_reason`) et `risk_contributions` (la part de risque de chaque
  placement, à partir de la covariance seulement). Le code retire une objection qui ne cite aucun appel qu'il a fait,
  ou qui cite un nombre absent à la fois de ses résultats cités et des faits qu'on lui a donnés (le client, les
  limites, les nombres de cette stratégie, ou la somme de deux de ses pondérations) (#45). Une correction vient d'un
  menu (fusionner deux placements, en réduire un, déplacer de la croissance vers le défensif, divulguer) et ne peut que
  **resserrer** une donnée d'entrée du calcul; tout le calcul du Portefeuille est alors relancé (recherche de
  répartition, statistiques, perspective, contrôles) et le Gardien revérifie contre les limites d'origine du client.
  En cas d'échec, l'original est conservé (« conservé, justifié »). Une ronde, une correction par stratégie (#30).
- **Sur un portefeuille déjà détenu :** le Critique le revoit avec les mêmes outils, en divulgation seulement (la
  reconstruction est la correction); l'Explicateur ajoute une section « Le portefeuille que vous avez déjà »;
  l'Analyste reçoit deux outils, `existing_portfolio` et `what_if_existing` (#42).
- **Analyste :** répond aux questions de suivi (« et si je mettais 10 % dans NVDA ? ») en appelant des outils, dont deux
  relancent le vrai pipeline, Gardien compris. Chaque nombre de sa réponse doit figurer dans un résultat d'outil qu'il
  cite; aucune formulation d'achat ou de vente; l'avertissement est ajouté par le code; sinon, la réponse déterministe
  la remplace (#35).

**L'Explicateur ne tape jamais un nombre.** Chaque % et chaque $ de ses faits est un identifiant (`{n7}`); il écrit des
identifiants et le code insère les valeurs, de sorte qu'un nombre qu'il aurait tapé lui-même est rejeté (décision #27).
**Son propre contrôle :** son seul outil, `check_text`, applique G11–G13 à son ébauche; il peut vérifier jusqu'à 3
fois avant de répondre. Le code revérifie ensuite le texte final : s'il échoue, ou en cas d'erreur AWS, un gabarit
déterministe (qui réussit par construction) le remplace et la trace dit pourquoi (#23).

**Langue.** Les deux applications ont un bouton Français ⇄ English (français par défaut), et tout est traduit :
l'interface, les textes du moteur (raisons, contrôles, répartitions, trace) au moment de l'affichage, avec les nombres
recopiés tels quels puis mis au format français, et les textes de Claude, qui rédige directement en français quand
l'application est en français (Explicateur, Critique, Analyste). Le Gardien accepte l'avertissement français (G11) et
vérifie les nombres sur le texte avant leur mise en forme (G12). Le gabarit de secours existe dans les deux langues (#49).

## 2. Méthodes, modèles et technologies, et pourquoi

- **Des règles là où la réponse doit être démontrable, un LLM là où la langue compte** (#2). Limites, nombres et
  verdicts sont déterministes : les mêmes réponses donnent toujours les mêmes limites et les 16 profils de test restent
  fiables. Le LLM lit le texte libre, décide quoi examiner, argumente et explique, dans des garde-fous; il ne fixe
  jamais une limite ni un nombre.
- **Pas d'optimiseur** (#1, #37) : des pondérations optimisées sur 5 ans incluant 2022 sont instables (DeMiguel,
  Garlappi et Uppal, 2009). Nous l'avons testé (l'optimiseur moyenne-variance de Joud, branche
  `optimisation-markowitz`) : le portefeuille « optimal » changeait avec la période et n'a pas battu l'équipondération
  hors échantillon; il reste donc hors de la démonstration. Ce qui n'exige pas de rendements moyens est utilisé (#40) :
  les **contributions au risque** (la part de risque de chaque placement, à partir de la covariance seulement) comme
  outil du Critique, et les **choix KYC** de Joud (trois paris à 50/50 → aversion au risque A) comme contre-vérification
  de la tolérance du client, signalée « à clarifier » en cas de désaccord, jamais comme limite; plus une question
  d'espérance qui plafonne les connaissances si la réponse est erronée. Les stratégies sont définies par ce qu'elles
  détiennent : cœur diversifié (XIU + SPY ou ESGV, obligations courtes et globales), revenu (sociétés à dividendes +
  XIU, obligations globales), orientation croissance (QQQ, grandes sociétés technologiques, obligations courtes et or;
  seulement pour un intérêt pour l'IA, la techno ou la crypto, un niveau de risque ≥ 3 et des connaissances ≥ 3). La
  crypto seulement si le client l'a demandée, que son profil le permet et que les données sont d'accord : avec la
  crypto, la part de croissance sous la limite de perte ne doit pas être plus basse que sans elle (#26).
- **Répartition et règle de perte finale (audit quantitatif intégré, décision #46).** La règle d'horizon et le plancher
  de liquidité demeurent. Le plafond de croissance parcourt un bootstrap par blocs stationnaire sur l'horizon du client
  et s'arrête avant que la probabilité simulée de dépasser son seuil de perte ne dépasse 10 %. La dérive centrale est
  l'encaisse plus une **prime annuelle de 3 % sur la partie croissance**, une hypothèse de l'équipe, pas une prévision.
  La sensibilité par sous-période est divulguée. Les pondérations finales sont vérifiées avec de nouvelles trajectoires
  simulées (G7/D2, tolérance d'échantillonnage comprise); G17 est intégré à G7, et G18 vérifie que statistiques,
  perspective, risque et contrôles décrivent les pondérations finales. La pire baisse historique reste descriptive. Le
  bootstrap ne peut pas créer de crises jamais vues; le seuil de 10 % du modèle n'est pas une garantie calibrée d'un
  taux de dépassement réel de 10 %.
- **Jusqu'à trois stratégies = trois niveaux de risque** (#32) : la croissance maximale permise par les limites du
  client, puis 10 et 20 points de moins en actions (chacune recalculée au complet avec un plancher défensif plus élevé,
  jamais au-delà des limites du client). La saveur préférée du client (croissance, cœur diversifié, revenu) prend le
  premier niveau. Les niveaux à moins de 5 points d'écart sont retirés : un client avec peu de marge (Robert) en reçoit
  deux, pas trois quasi-copies.
- **Plafonds par société et par client** (#24) : la pire baisse 2021–2026 d'une société, à sa pondération, peut coûter au
  plus ¼ de la limite de perte du client, et aucune société ne dépasse ⅕ de ce que le client peut détenir en actions.
  La crypto (BTC + ETH) est un seul pari sous la même règle. Les débutants ont la moitié du budget et pas de crypto.
- **Transparence des FNB** (#6) : pondération directe + pondération détenue à travers les FNB (fichiers des émetteurs).
- **Un portefeuille déjà détenu** (#42, #44) : saisi ligne par ligne ou en texte libre (« j'ai 10 000 $ dans XIU »; le
  montant doit figurer dans le texte). Il reçoit les mêmes contrôles que toute stratégie, une critique écrite à partir
  de ces nombres, ses frais annuels de fonds en $ (le ratio de frais propre à chaque fonds; frais inconnus listés,
  jamais 0) et les mouvements en $ vers la première stratégie proposée. Pas d'optimiseur (#1, #37). Un fonds sans
  données est mesuré avec un **substitut identifié** qui suit le même indice ou un indice proche (22 fonds,
  `dh.standins`); les fonds couverts en CAD (XSP.TO…) prennent le rendement en USD de la source plus l'écart de taux
  du financement à un jour Canada–États-Unis. Un fonds à composition propre (ZEQT) est laissé de côté, et c'est dit.
- **Technologies :** Python, pandas/numpy/scipy; Strands Agents SDK; Amazon Bedrock (Claude Opus 5.5,
  `global.anthropic.claude-opus-5-5`, us-east-1, un seul modèle par défaut pour tous les agents, #45); Amazon S3;
  Streamlit pour les deux applications (hébergées sur Streamlit Community Cloud, données tirées de S3 au premier
  démarrage). Voix facultative dans l'interface guidée : Amazon Transcribe (parole → texte, français ou anglais du
  Canada) et Amazon Polly (texte → parole), désactivée sauf si `AF_VOICE_ENABLED=1`; l'audio passe par S3 sous
  `voice/` et est supprimé une fois transcrit.
- **Pourquoi ces services AWS** (diapositive 7 : un vrai rôle, aucun service ajouté pour impressionner) : **Bedrock**
  exécute les quatre étapes qui exigent du jugement ou de la langue (Extracteur, Critique, Explicateur, Analyste); le
  **Strands Agents SDK** donne à chacun ses outils et sa boucle d'outils; **S3** conserve les preuves de chaque
  exécution, pour que toute réponse puisse être auditée après coup, et fournit les données à l'application hébergée;
  **Transcribe et Polly** (facultatifs) permettent de parler au lieu de taper, pour l'accessibilité. Bedrock AgentCore
  Runtime était prévu pour héberger le pipeline et n'est pas déployé. Les réponses Bedrock sont enregistrées et
  versionnées (`cache/`), pour que la démonstration rejoue les vraies réponses des agents après la fermeture du compte.

## 3. Sources, actifs retenus, traitement, hypothèses

- **Jeu de départ** (organisateurs) : 31 actifs (10 actions canadiennes et 10 américaines, 9 FNB dont des obligations,
  de l'or et un fonds à filtre ESG, BTC, ETH), quotidiens 2021-11-12 → 2026-11-12, de Yahoo Finance; USD/CAD et taux
  canadiens de la Banque du Canada; taux, IPC et chômage américains de FRED.
- **Avoirs des FNB :** fichier quotidien de SPY de State Street, au 2026-11-12 (503 titres, `CONTEXT.md`). QQQ, ESGV et
  XIU non chargés : pour ces FNB, la transparence et les contrôles de secteur sont des bornes inférieures, et les
  contrôles le disent.
- **Obligations :** titres gouvernementaux canadiens et américains, modalités et dates tirées de sources publiques
  (`scripts/build_fixed_income.py`, `data/README.md`); ce sont des références, pas des offres exécutables.
- **Traitement :** rendements simples quotidiens sur le cours ajusté; tout converti en CAD au taux de la Banque du
  Canada; un seul calendrier de jours ouvrables pour tous les actifs (fins de semaine crypto retirées); annualisation
  avec le nombre de lignes observées par année (#12). Fenêtre de la soumission : celle du jeu de départ (#48).
- **Hypothèses (toutes écrites dans `rules.py` et les décisions) :** les points d'ancrage de l'horizon (2 et 15 ans);
  ¼ et ⅕ dans les plafonds par société; le volet capacité de la limite de perte (selon le niveau de capacité du
  client); la probabilité de 50 % pour le plancher d'objectif; la prime de 3 % et le seuil de 10 % du modèle de perte;
  les seuils de diversification (#20). Les profils sont fictifs.
- **Licences :** données utilisées pour un prototype éducatif non commercial; fichiers bruts non redistribués (#11).

## 4. Mécanisme d'explicabilité, avec un exemple complet

**Mécanisme.** Chaque limite porte une raison écrite; chaque stratégie porte ses nombres et la note de chaque
ajustement; chaque relais est une étape de la trace (qui → qui, quoi, ✔/⚠/✘). L'Explicateur ne voit que `facts`, un
petit JSON dont les nombres sont déjà mis en forme comme le texte doit les montrer : il recopie au lieu de calculer.
La trace montre des étapes, des nombres et des verdicts, jamais le raisonnement brut du modèle (énoncé p. 17, #9).
Chaque exécution est enregistrée dans S3.

**Exemple : Robert demande 25 % dans Tesla** (`make explain P=robert`).
1. **Profileur :** tolérance 2 (il conserverait ses placements lors d'une baisse de 20 %, mais accepte au plus 15 % : la
   réponse la plus prudente l'emporte); capacité 2 (horizon de 4 ans); limite de perte 15 %, soit 60 000 $ sur
   400 000 $; horizon de 4 ans → au plus environ 15 % en actions. Tesla : pire baisse 2021–2026 de −70,9 %; à 25 %,
   elle seule coûterait −17,7 % du portefeuille, plus que toute sa limite de perte de 15 %; elle entre dans ses limites
   jusqu'à 3,1 %.
2. **Portefeuille :** cœur diversifié 15/85, pire baisse −8,6 %, 2022 −5,8 %; revenu 5/95, pire baisse −7,7 % (lignes
   finales `persona-strategies`, commit source 9a2febb).
3. **Gardien :** les deux stratégies sont vérifiées par les règles de perte, de diversification et de cohérence; les
   avoirs de FNB manquants sont divulgués; Tesla n'est dans aucune des deux (G9).
4. **Critique** (Opus 5.5) : appelle ses outils sur les deux stratégies, p. ex. les corrélations entre placements, les
   contrôles les plus près de leur limite, la part de risque de chaque placement; chaque objection cite un résultat
   d'outil; une correction, s'il y en a une, est recalculée et revérifiée. La trace liste chaque appel et ce qui est
   advenu de chaque objection.
5. **Demande côte à côte :** 25 % dans Tesla « telle que demandée » et « ce qui convient », avec les mêmes contrôles.
6. **Explicateur** (Opus 5.5, une autovérification) : « En 2021-2026, la pire baisse de TSLA a été de −70,9 %. À 25 %,
   ce placement à lui seul aurait coûté −17,7 % du portefeuille, soit plus que toute votre limite de perte de 15 %.
   TSLA entre dans vos limites jusqu'à 3,1 %. La décision vous appartient; nous montrons seulement ce qui respecte les
   limites que vous nous avez données. » (Texte produit en anglais; traduit ici.)
7. **Gardien sur le texte :** G11 avertissement ✔, G12 chaque % tracé ✔, G13 Tesla expliquée ✔. Exécution enregistrée
   dans S3.
8. **Question de suivi (Analyste) :** « Et si je mettais 10 % dans Tesla ? » relance le pipeline avec cette position et
   répond avec les nombres obtenus et les règles enfreintes.

## 5. Validation, limites, améliorations

**Validation.** Évaluation chiffrée complète sur une page : [`EVALUATION.md`](EVALUATION.md) (`scripts/evaluate.py`, `results.csv`, expérience `evaluation`) : 16/16 profils, 217/217 nombres du texte client vérifiés, 200/200 faux nombres détectés, 10/10 cas pièges, et le calibrage honnête du modèle de perte.
- 16 profils de test avec verdicts attendus (`make scenarios`) : 16/16 (`results.csv`). Ils comprennent des échecs
  voulus (une stratégie qui applique Tesla en douce, une explication avec un nombre inventé, un avertissement absent)
  pour montrer que le Gardien les attrape. Ils testent les règles, pas de vrais portefeuilles (#7).
- La suite de régression hors ligne (`make test`) : données synthétiques, AWS simulé; p. ex. la répartition ne dépasse
  jamais la limite de perte et est la plus grande qui convient; le texte de l'Explicateur est remplacé quand il
  enfreint une règle; l'interface fonctionne en français et en anglais.
- **Les agents sont testés contre leurs contrôles** avec un modèle simulé : une objection du Critique qui cite un
  nombre qu'aucun outil n'a rendu est retirée; au-delà de 3 objections ou de 6 appels d'outils, c'est coupé; une
  correction qui enfreindrait une limite est annulée; un nombre de l'Extracteur absent du texte du client est retiré;
  une réponse de l'Analyste avec un nombre non appuyé est remplacée; une erreur AWS bascule vers la version
  déterministe et la trace dit pourquoi.

**Limites.**
- Les nombres historiques décrivent la période des données : sur le jeu de départ 2021–2026, un seul marché baissier
  modéré en CAD; ce ne sont pas des prévisions, et les baisses futures peuvent être plus fortes. Biais du survivant :
  les 31 actifs ont été choisis en 2026, ce qui flatte tout rendement passé (actions équipondérées +21 %/an contre
  SPY +14,5 %, audit).
- Les points d'ancrage de l'horizon (2 et 15 ans) décident la plupart des répartitions; c'est un jugement assumé, pas
  une mesure.
- Les hypothèses du §3 sont explicables, mais non calibrées au-delà de cette période.
- L'Explicateur ne peut pas taper un nombre (il écrit des identifiants que le code remplit), mais il pourrait placer un
  vrai nombre à côté de la mauvaise étiquette; G12 ne le voit pas. Il en va de même des vérifications de nombres du
  Critique et de l'Analyste, et de la vérification d'ancrage de l'Extracteur (le nombre est dans le texte, pas
  forcément rattaché au bon champ).
- Les réponses des agents varient d'une exécution à l'autre; la démonstration rejoue des réponses Bedrock versionnées,
  et une nouvelle exécution peut différer.
- Seuls les avoirs de SPY sont chargés; 3 des 4 FNB d'actions sont traités comme des blocs.
- Substituts pour les fonds sans données : les non couverts reproduisent la pire baisse du vrai fonds à ±0,4 point
  près; les couverts en CAD la sous-estiment de 1 à 3 points (`results.csv`, `standin-*`). Le vrai nombre est affiché
  à côté de chaque substitut.
- Les frais des fonds sont montrés en $, mais pas déduits des rendements historiques; pas d'impôts ni de types de
  comptes (CELI/REER); un seul objectif par exécution.

**Testé et écarté.** Une stratégie protégée (CPPI, #21) et deux optimiseurs moyenne-variance (#37) : sur une seule
période de 5 ans, leurs pondérations changeaient avec la période et n'ont pas battu l'équipondération hors
échantillon; les stratégies restent donc définies par ce qu'elles détiennent, avec une répartition fixée par les
limites du client.

**Améliorations.** Calibration indépendante du modèle de perte simulé et de ses hypothèses de prime; plafonds par
société tirés de la pire de deux sous-périodes; volet capacité de la limite de perte tiré du bilan du client; les
autres avoirs de FNB; plusieurs objectifs par client; hébergement du pipeline sur Bedrock AgentCore; traduction des
textes produits par les agents.

## Reproduire
```
make setup && make data && make check     # données : CSV du jeu de départ dans data/raw/
make scenarios && make test               # validation, hors ligne
make explain P=robert                     # pipeline complet + Critique + Explicateur (Bedrock avec .env, sinon réponses enregistrées)
make extract T="I'm 59, retiring in 4 years, put 25% in Tesla"   # texte libre → profil (hors ligne : anglais seulement)
make warm                                 # avec .env : remplir toutes les réponses enregistrées, puis versionner cache/
make app                                  # démonstration (agents, trace); make ui : interface guidée
```
Windows : `python -m dh check`, `python -m dh explain robert`, `python -m pytest -q`,
`python -m streamlit run interface/app.py`.
