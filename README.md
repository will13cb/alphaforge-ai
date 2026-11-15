# AlphaForge AI : un analyste en placement qui sait dire non

**Robert, 59 ans, veut mettre 25 % de son portefeuille dans Tesla.** Il accepte de perdre au plus 15 %.
AlphaForge AI calcule que la pire baisse de Tesla sur 2021-2026 a été de −70,9 % : à 25 %, Tesla seule aurait
coûté −17,7 % du portefeuille, plus que toute sa limite de perte. Tesla entre dans ses limites jusqu'à 3,1 %.
L'outil lui montre la règle, le nombre et la source, puis lui laisse la décision.

**Essayer :** https://alphaforge-ai-wj.streamlit.app/ (français par défaut, bouton Français ⇄ English)
· *Simulation seulement : profils fictifs, aucune transaction, pas un conseil financier.*

Datathon PolyFinances 2026 (Polytechnique Montréal), défi **AlphaForge AI** de la **Banque Nationale × AWS**.
Équipe : William Caron-Bastarache, Joud Katbe. *English version: [`README.en.md`](README.en.md).*

**En une phrase :** des agents spécialisés (Strands sur Amazon Bedrock, Claude Opus 5.5) établissent le profil
de l'investisseur comme un conseiller canadien, proposent jusqu'à trois stratégies simulées, et c'est le code,
pas le LLM, qui fait respecter les limites. Chaque exécution laisse une trace dans Amazon S3.

## Ce que ça fait

On entre le profil d'un client. Le pipeline établit ses limites (chacune avec sa raison écrite), construit jusqu'à
trois stratégies à des niveaux de risque différents, fixe la répartition actions / obligations de chacune comme la plus
stricte des contraintes du client (une règle d'horizon assumée, l'argent requis bientôt, la probabilité simulée de
dépasser son seuil de perte sur son horizon) et dit laquelle a décidé, vérifie tout par des règles explicites, puis
explique le résultat en mots simples en reliant chaque nombre aux données.

## Comment ça fonctionne

| Étape | Agent | Comment | Résultat | État |
|---|---|---|---|---|
| 0 | Extracteur | agent Strands, outil `check_profile` | les champs du profil à partir d'une description libre; chaque nombre doit figurer dans le texte du client; les éléments essentiels manquants sont demandés (#29) | construit, réponses Bedrock enregistrées |
| 1 | Profileur | règles | tolérance, capacité, connaissances, limite de perte (aussi en $), plancher défensif (horizon, retraits), plafonds par société et pour la crypto, chacun avec sa raison; contre-vérification KYC (#40) | construit |
| 2 | Données de marché | déterministe | par actif : rendement, volatilité, pire baisse, CVaR, 2022, corrélations, perspective d'objectif | construit |
| 3 | Portefeuille | règles + données | jusqu'à 3 stratégies à des niveaux de risque différents (#32); répartition = la plus stricte de la règle d'horizon, des retraits et du test de perte simulé, avec celle qui a décidé (#33); contrôles de diversification C–F | construit |
| 4 | Critique | agent Strands avec outils | enquête (11 outils dont les contributions au risque, ≤ 6 appels), ≤ 3 objections appuyées, une correction recalculée par stratégie, revérifiée par le Gardien (#30, #40) | construit, réponses Bedrock enregistrées |
| 5 | Explicateur | agent Strands, Claude Opus 5.5 sur Bedrock | le texte au client à partir de faits préformatés; vérifie sa propre ébauche avec les règles du Gardien (outil) | construit |
| app | Analyste | agent Strands avec outils | questions de suivi (en français ou en anglais) : les scénarios relancent le pipeline, chaque nombre de la réponse est vérifié par le code | construit, réponses Bedrock enregistrées |
| tous | Gardien | règles, dont G7 (perte simulée) et G18 (cohérence) | ✔ / ⚠ / ✘ à chaque étape; ✘ sur le profil → on demande; sur une stratégie → retirée; sur une correction du Critique → l'original est gardé; sur le texte → gabarit | construit |
| tous | Stockage des traces | Amazon S3 | chaque exécution en JSON dans `s3://$S3_BUCKET/traces/` (copie locale de secours) | construit |

**Les agents enquêtent et argumentent, le code fait respecter.** Les agents Strands sur Amazon Bedrock décident quoi
écrire ou vérifier; `pipeline.py` fixe l'ordre pour que le Gardien s'exécute toujours; les preuves de chaque exécution
vont dans Amazon S3. Les limites suivent le client et les données (horizon, limite de perte, pire baisse propre à
chaque actif), pas une table fixe. Les contrôles de convenance du Gardien sont *calqués sur* les obligations
canadiennes de connaissance du client et de convenance (Règlement 31-103, art. 13.2–13.3); ils ne constituent pas un
test de conformité juridique. Chaque relais entre agents est inscrit dans une trace (étapes, nombres, verdicts, jamais
le raisonnement brut du modèle).

- Graphe de l'orchestration : [`aws/architecture.md`](aws/architecture.md) (image :
  [`aws/architecture.png`](aws/architecture.png))
- Livrables en français : [`deliverables/ONE_PAGER.md`](deliverables/ONE_PAGER.md),
  [`deliverables/TECHNICAL_DOC.md`](deliverables/TECHNICAL_DOC.md),
  [`deliverables/VIDEO_SCRIPT.md`](deliverables/VIDEO_SCRIPT.md)
- Conception et agents : [`notes/system-design.md`](notes/system-design.md) · ce que chaque agent transmet :
  [`notes/contract.md`](notes/contract.md) · chaque décision et sa raison : [`notes/decisions.md`](notes/decisions.md)
  (notes de travail de l'équipe, en anglais)

### État

| Construit | Non fait |
|---|---|
| Profileur, données de marché, Portefeuille (répartition calculée, plafonds par société, contrôles C–F, demande côte à côte), Gardien (contrôles de perte et de cohérence), agents Strands sur Bedrock (Opus 5.5) : Extracteur, Critique, Explicateur, Analyste; revue d'un portefeuille déjà détenu (substituts identifiés, frais, reconstruction en $); recherche d'obligations détenues jusqu'à l'échéance (titres gouvernementaux sourcés); interface guidée (voix facultative : Amazon Transcribe + Polly; choix KYC et question d'espérance en contre-vérification); bouton Français ⇄ English; stockage des traces dans S3; application de démonstration; 16 profils de test; tests hors ligne | Hébergement sur Bedrock AgentCore non déployé; avoirs des FNB QQQ / ESGV / XIU (SPY chargé) |

## Démarrage rapide

Exige Python 3.12+ et un accès Internet (pour construire les données).

```bash
make setup        # environnement virtuel + dépendances + .env (à remplir)
make data         # CSV du jeu de départ dans data/raw/
make check        # rendement / volatilité / Sharpe / pire baisse par actif
make scenarios    # 16 profils de test à travers le Profileur et le Gardien, chaque relais affiché
make explain P=robert   # pipeline complet + Critique + Explicateur sur un profil (amira, mateo, robert); trace dans S3
make test         # tests hors ligne
make extract T="J'ai 59 ans, ..."   # texte libre → profil + questions de suivi
make bedrock-check  # vérification AWS : région, identifiants, Bedrock texte + outils, S3 (exige .env)
make app          # la démonstration (vue du jury) sur http://localhost:8501 : limites, stratégies, explication, Analyste, trace
make ui           # interface guidée (vue client) sur http://localhost:8502 : même moteur, questions pas à pas
make warm         # avec Bedrock : remplit toutes les réponses enregistrées de la démo (DRY=1 liste les appels)
```

**Deux interfaces, un seul moteur.** `make app` est la démonstration : elle montre tout ce que les agents ont fait
(limites et raisons, stratégies et ce qui a fixé chaque répartition, contrôles du Gardien, texte de l'Explicateur,
questions de suivi, trace complète) et enregistre la trace de chaque exécution dans Amazon S3. `make ui` est ce qu'un
client utiliserait : une question à la fois, résultats essentiels d'abord, l'Analyste en conversation, et la revue d'un
portefeuille déjà détenu. Les deux appellent le même `pipeline.run`; aucune ne calcule un nombre elle-même. Les deux
offrent un mode clair / sombre, l'activité des agents en direct et un bouton Français ⇄ English (les textes produits
par le moteur et les agents restent en anglais : le Gardien vérifie ce texte-là).

**Modèle de risque.** Le plafond de croissance utilise un bootstrap par blocs stationnaire sur l'horizon du client, une
prime annuelle assumée de 3 % des actifs de croissance au-dessus de l'encaisse et un seuil de dépassement de 10 %. Une
nouvelle simulation vérifie les pondérations finales. Ce sont des hypothèses de scénario, pas une garantie calibrée
des pertes futures (`notes/risk-architecture.md`).

Windows sans `make` :

```bash
python -m venv .venv && .venv\Scripts\python -m pip install -e ".[dev,agents]"
copy Datathon2026Infos\alphaforge_starter\build_dataset.py data\raw\ && .venv\Scripts\python data\raw\build_dataset.py
.venv\Scripts\python -m dh check
.venv\Scripts\python -m dh scenarios -v
.venv\Scripts\python -m dh explain robert
set LLM_PROVIDER=mock && .venv\Scripts\python -m pytest -q
.venv\Scripts\python -m streamlit run interface/app.py
```

### Configuration (`.env`, jamais versionné)

| Variable | Usage |
|---|---|
| `LLM_PROVIDER` | `mock` (hors ligne, par défaut) ou `bedrock` |
| `BEDROCK_MODEL_ID` | modèle Bedrock des agents (vérifié sur le compte de l'événement : `global.anthropic.claude-opus-5-5`) |
| `AWS_REGION` | p. ex. `us-east-1` |
| `S3_BUCKET` | compartiment des traces (`traces/`) et des données (`raw/`; `make data` peut s'en servir) |
| `AF_LANG` | langue de l'interface au démarrage : `fr` (par défaut) ou `en` |

Les identifiants AWS viennent de votre profil AWS (`aws configure`), pas de ce dépôt. Les réponses de Claude pour les
trois profils de démonstration sont enregistrées dans `cache/` : quand les faits concordent, elles sont rejouées sans
AWS; sinon, le mode hors ligne utilise une version déterministe, indiquée comme telle à l'écran.

## Déploiement (Streamlit Community Cloud)

Les données ne vont jamais dans git (décision #11). Une copie hébergée les obtient au premier démarrage : depuis le
compartiment S3 de l'équipe, sinon en les reconstruisant avec le script des organisateurs (`src/dh/bootstrap.py`),
sur la période du jeu de départ (2021-11-12 → 2026-11-12, décision #48).

1. Une fois, depuis un ordinateur qui a les données et le `.env` : `make data-up` (téléverse `data/raw/*.csv` dans
   `s3://$S3_BUCKET/raw/`).
2. Sur https://share.streamlit.io : **New app** → ce dépôt, branche `main`, fichier `interface/app.py` (interface
   guidée) ou `app/app.py` (démonstration); **Advanced settings** → Python 3.12.
3. **Secrets** (jamais dans git) :
   ```toml
   AF_AUTO_DATA = "1"
   S3_BUCKET = "…"
   AWS_REGION = "us-east-1"
   AWS_ACCESS_KEY_ID = "…"
   AWS_SECRET_ACCESS_KEY = "…"
   AWS_SESSION_TOKEN = "…"
   LLM_PROVIDER = "bedrock"
   AF_LANG = "fr"
   AF_VOICE_ENABLED = "0"   # "1" active la voix dans l'interface guidée (Amazon Transcribe + Polly, audio via S3 voice/)
   ```
   Après la fermeture du compte de l'événement, mettre `LLM_PROVIDER = "mock"` et retirer les clés AWS : l'application
   reconstruit elle-même les données et rejoue les réponses enregistrées de Claude (mode hors ligne, indiqué à l'écran).

## Données

| Source | Contenu | Provenance |
|---|---|---|
| Jeu de départ (organisateurs) | 31 actifs, prix quotidiens 2021-11-12 → 2026-11-12, dividendes et fractionnements, USD/CAD, taux, IPC | Yahoo Finance, Banque du Canada, FRED; reconstruit par `Datathon2026Infos/alphaforge_starter/build_dataset.py` |
| Avoirs des FNB | ce que SPY, QQQ, ESGV et XIU détiennent réellement, pour la transparence | fichiers des émetteurs; `scripts/build_holdings.py`. SPY chargé (au 2026-11-12) |
| Obligations | titres gouvernementaux canadiens et américains, détenus jusqu'à l'échéance | sources publiques datées; `scripts/build_fixed_income.py` (`data/README.md`) |

Prix dans la devise de chaque actif, convertis en CAD; rendements à partir du cours ajusté. Limites connues : biais du
survivant dans l'univers, données macro mensuelles datées par mois de référence, avoirs = un instantané utilisé pour
l'exposition seulement. Les nombres historiques décrivent le passé; ce ne sont pas des prévisions. Sources, dates,
traitement et conditions : [`data/README.md`](data/README.md). Les fichiers de données ne sont jamais versionnés.

## Validation

`make scenarios` fait passer 16 profils fictifs (les trois personas de l'énoncé et des pièges : un débutant qui veut
100 % de bitcoin, un horizon court avec un fort appétit pour le risque, aucun fonds d'urgence, un nombre inventé dans
l'explication…) contre leurs verdicts attendus : 16/16. `make test` exécute la suite de régression hors ligne
(données synthétiques, AWS simulé), y compris la recherche de répartition, le gabarit de secours de l'Explicateur et
les contrôles de chaque agent (un nombre non appuyé est retiré, une correction du Critique qui enfreint une limite est
annulée) et les deux langues de l'interface.

## Organisation du dépôt

```
src/dh/            data.py (chargement, change, calendrier) · metrics.py (statistiques de risque, transparence)
                   i18n.py + i18n_fr.py (Français ⇄ English) · tracestore.py (traces S3) · llm.py · kyc.py
src/dh/agents/     profiler · market · portfolio · checks · guardian · critic · explainer · analyst · extractor
                   existing (portefeuille déjà détenu) · fixed_income · pipeline · trace · rules · scenarios
app/app.py         application de démonstration (vue du jury)
interface/         interface guidée (vue client)
aws/               graphe de l'architecture
cache/             réponses enregistrées de Claude (démonstration hors ligne)
deliverables/      fiche d'une page, documentation technique, script vidéo (anglais : *.en.md)
Datathon2026Infos/ énoncé officiel, diapositives, script du jeu de départ
tests/             tests hors ligne
```

## Licence

MIT, voir [`LICENSE`](LICENSE).
