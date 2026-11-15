# AlphaForge AI : un analyste en placement qui sait dire non, et qui montre pourquoi

**Robert, 59 ans, veut mettre 25 % de son portefeuille dans Tesla.** Il accepte de perdre au plus 15 %.
AlphaForge AI calcule que la pire baisse de Tesla sur 2021-2026 a été de −70,9 % : à 25 %, Tesla seule aurait coûté
−17,7 % du portefeuille, plus que toute sa limite de perte. Tesla entre dans ses limites jusqu'à 3,1 %.
L'outil lui montre la règle, le nombre et la source, puis lui laisse la décision.

> **Essayer maintenant :** https://alphaforge-ai-wj.streamlit.app/ · en français par défaut, bouton Français ⇄ English
>
> **Livrables :** [fiche d'une page](deliverables/ONE_PAGER.md) · [documentation technique](deliverables/TECHNICAL_DOC.md)
> · [script de la vidéo](deliverables/VIDEO_SCRIPT.md) · [architecture](aws/architecture.md)

Datathon PolyFinances 2026 (Polytechnique Montréal) · défi **AlphaForge AI** de la **Banque Nationale × AWS** ·
équipe William Caron-Bastarache et Joud Katbe · *English: [`README.en.md`](README.en.md)*

*Simulation seulement : profils fictifs, aucune transaction réelle, pas un conseil financier.*

---

## Le problème

Un investisseur voit tous les prix, mais pas ce qu'un portefeuille signifie **pour lui** : combien il peut perdre, de
combien de temps il dispose, si une action à la mode lui convient. Une cote de risque générique ne le
lui dit pas, et un assistant conversationnel laissé à lui-même risque de répondre par un « oui » poli ou un chiffre inventé. AlphaForge AI fait
ce que ferait un bon conseiller canadien : il établit le profil, propose ce qui convient, refuse ce qui ne convient pas,
et **justifie chaque nombre**.

## Ce qui nous distingue

| | En pratique |
|---|---|
| **Des agents qui enquêtent, du code qui fait respecter** | Quatre agents Strands sur Amazon Bedrock (Claude Opus 5.5) choisissent quoi vérifier et comment l'expliquer. Mais chaque limite et chaque nombre viennent du code : le Gardien applique 17 règles calquées sur les obligations canadiennes de connaissance du client (Règlement 31-103), et il s'exécute toujours. |
| **Un Critique qui vérifie avant d'objecter** | Le Critique appelle jusqu'à 6 outils (corrélations, part de risque de chaque placement, crise de 2022…) et formule au plus 3 objections, chacune appuyée par un résultat obtenu. S'il propose une correction, tout le calcul est relancé et le Gardien revérifie; si la correction enfreint une limite, l'original reste. |
| **Aucun nombre inventé** | L'Explicateur n'écrit jamais un chiffre : il place des repères que le code remplit avec les valeurs calculées. Les nombres du Critique et de l'Analyste doivent venir des outils qu'ils citent. Un texte qui échoue est remplacé par un gabarit vérifié, et la trace le dit. |
| **Des limites propres à chaque client, et expliquées** | Pas de table de profils types : la limite de perte, le plancher défensif et le plafond de chaque société sont calculés pour le client, chacun avec sa raison écrite. Chaque stratégie dit quelle contrainte a fixé sa répartition. |
| **Honnête sur ses limites** | Nous avons testé un optimiseur de Markowitz et une stratégie protégée (CPPI), puis les avons écartés, preuves à l'appui : les pondérations « optimales » changeaient avec la période et n'ont pas battu l'équipondération hors échantillon. Aucun rendement passé n'est présenté comme une prévision. |
| **Utile au vrai client** | Questions guidées ou description libre, revue du portefeuille qu'on détient déjà (frais en $, mouvements en $), recherche d'obligations détenues jusqu'à l'échéance, application entièrement en français ou en anglais (interface, résultats et textes de Claude), voix facultative. |

## Visite de deux minutes

Dans l'[application](https://alphaforge-ai-wj.streamlit.app/) :

1. **Accueil → « Essayer avec un client fictif »**, puis lancer l'analyse. *Vos limites* : chaque limite avec sa raison.
2. **Vos résultats** : jusqu'à trois stratégies côte à côte, leur pire baisse passée, leur comportement en 2022, ce qui a
   fixé leur répartition, et les contrôles réussis ou à savoir.
3. **Activité** : chaque relais entre agents, les appels d'outils du Critique, les verdicts du Gardien, l'endroit où la
   preuve a été enregistrée (Amazon S3).
4. **Assistant** : cliquer « Et si je mettais 10 % dans Tesla ? ». L'Analyste relance tout le pipeline avec cette position
   et répond avec les nombres obtenus.
5. **« J'ai déjà un portefeuille »** : saisir ses placements (ou « Essayer un portefeuille fictif ») pour obtenir une
   critique chiffrée et la reconstruction vers une stratégie qui convient.

## Comment ça fonctionne

![Architecture d'AlphaForge AI](aws/architecture.png)

*Jaune : là où le code décide. Bleu : les agents Strands. Détails : [`aws/architecture.md`](aws/architecture.md).*

| Étape | Rôle | Qui décide |
|---|---|---|
| **Extracteur** | lit la situation décrite en mots libres et remplit le profil; ne garde un nombre que s'il figure dans le texte; demande ce qui manque | agent (Bedrock) + contrôles du code |
| **Profileur** | transforme le profil en limites : niveau de risque, perte maximale (en % et en $), plancher défensif, plafond par société et pour la crypto, chacune avec sa raison | code |
| **Données de marché** | 31 actifs en CAD : volatilité, pire baisse, CVaR, crise de 2022, corrélations | code |
| **Portefeuille** | jusqu'à 3 stratégies à des niveaux de risque différents, répartition calculée et justifiée, contrôles de diversification à travers les FNB | code |
| **Gardien** | 17 règles : ✔ réussi, ⚠ à divulguer, ✘ la stratégie est retirée, avec la raison | code |
| **Critique** | enquête avec 11 outils, ≤ 3 objections appuyées, une correction recalculée par stratégie | agent (Bedrock) + code |
| **Explicateur** | rédige la réponse en mots simples; le Gardien vérifie le texte (avertissement, chaque nombre tracé, chaque demande expliquée) | agent (Bedrock) + code |
| **Analyste** | répond aux questions de suivi; ses scénarios relancent tout le pipeline | agent (Bedrock) + code |

Un agent décide *à l'intérieur* de son étape, jamais de l'étape suivante : l'ordre est fixé par `pipeline.py`, pour que
le Gardien ne puisse jamais être contourné.

## AWS : un vrai rôle pour chaque service

| Service | Ce qu'il fait dans AlphaForge |
|---|---|
| **Amazon Bedrock** (Claude Opus 5.5) | fait raisonner les quatre agents : Extracteur, Critique, Explicateur, Analyste |
| **Strands Agents SDK** | donne à chaque agent ses outils déterministes et sa boucle d'appels, plafonnée et tracée |
| **Amazon S3** | conserve la trace complète de chaque exécution (profil, limites, stratégies, contrôles, texte) pour l'audit, et fournit les données à l'application hébergée |
| **Amazon Transcribe et Amazon Polly** | voix facultative dans l'interface guidée : dicter sa situation, écouter la réponse |

Les réponses de Claude pour les clients de démonstration sont enregistrées dans le dépôt (`cache/`) : l'application
continue de les rejouer après la fermeture du compte AWS de l'événement, et l'indique à l'écran.

## Exemple complet : Robert

| | Résultat (données 2021-2026, `results.csv`) |
|---|---|
| Limite de perte | 15 %, soit 60 000 $ sur 400 000 $ (la plus prudente de ce qu'il accepte et de ce que sa situation permet) |
| Demande | 25 % dans Tesla : pire baisse −70,9 %, coûterait à elle seule −17,7 % du portefeuille; entre dans ses limites jusqu'à 3,1 % |
| Stratégie 1 | 15 % en actions; pire baisse passée −8,6 %; 2022 : −5,8 %; répartition fixée par son horizon de 4 ans |
| Stratégie 2 | 5 % en actions; pire baisse passée −7,7 % |
| Gardien | les deux stratégies passent; Tesla n'est dans aucune; la demande est expliquée, pas appliquée en douce |

## Validation

- **16 profils de test** avec verdicts attendus, dont des pièges (un débutant qui veut 100 % de bitcoin, un horizon de
  2 ans avec un fort appétit pour le risque, une explication avec un nombre inventé) : **16/16** (`make scenarios`).
- **Plus de 400 tests hors ligne** (`make test`), y compris les contrôles de chaque agent : un nombre non appuyé est
  retiré, une correction qui enfreint une limite est annulée, une erreur AWS bascule vers la version déterministe.
- **Substituts vérifiés** : un fonds sans données est mesuré par un substitut identifié; contre les vrais prix, l'écart
  sur la pire baisse est de ±0,4 point (1 à 3 points pour les fonds couverts en CAD, divulgué à l'écran).

## Limites assumées

- Les nombres décrivent 2021-2026 (un seul marché baissier modéré) : ce ne sont pas des prévisions.
- La règle d'horizon (aucune action à 2 ans, aucun plafond à 15 ans) est un jugement de l'équipe, présenté comme tel.
- Le modèle de perte simulé repose sur des hypothèses déclarées (prime de 3 %, seuil de 10 %), pas sur une garantie.
- Frais montrés mais non déduits; pas d'impôts ni de types de comptes (CELI/REER); un seul objectif à la fois.

Détails, sources et hypothèses : [documentation technique](deliverables/TECHNICAL_DOC.md).

---

<details>
<summary><b>Installer et lancer en local</b></summary>

Exige Python 3.12+ et un accès Internet (pour construire les données).

```bash
make setup        # environnement virtuel + dépendances + .env (à remplir)
make data         # données du jeu de départ dans data/raw/
make ui           # interface guidée (vue client) : http://localhost:8502
make app          # démonstration (vue du jury) : http://localhost:8501
make scenarios    # 16 profils de test, chaque relais affiché
make test         # tests hors ligne
make explain P=robert   # pipeline complet sur un persona (amira, mateo, robert); trace dans S3
make warm         # avec Bedrock : enregistre les réponses de démonstration
```

Windows sans `make` :

```bash
python -m venv .venv && .venv\Scripts\python -m pip install -e ".[dev,agents]"
copy Datathon2026Infos\alphaforge_starter\build_dataset.py data\raw\ && .venv\Scripts\python data\raw\build_dataset.py
set LLM_PROVIDER=mock && .venv\Scripts\python -m pytest -q
.venv\Scripts\python -m streamlit run interface/app.py
```

Configuration (`.env`, jamais versionné) : `LLM_PROVIDER` (`mock` hors ligne ou `bedrock`), `BEDROCK_MODEL_ID`
(`global.anthropic.claude-opus-5-5`), `AWS_REGION`, `S3_BUCKET`, `AF_LANG` (`fr` ou `en`). Les identifiants AWS
viennent de votre profil AWS, jamais de ce dépôt.
</details>

<details>
<summary><b>Déployer sur Streamlit Community Cloud</b></summary>

Les données ne vont jamais dans git. Au premier démarrage, l'application les prend dans le compartiment S3 de l'équipe,
sinon les reconstruit avec le script des organisateurs, sur la période du jeu de départ (2021-11-12 → 2026-11-12).

1. Une fois, depuis un ordinateur qui a les données : `make data-up` (téléverse `data/raw/` dans `s3://$S3_BUCKET/raw/`).
2. Sur https://share.streamlit.io : **New app** → ce dépôt, branche `main`, fichier `interface/app.py` (ou `app/app.py`
   pour la démonstration); Python 3.12.
3. **Secrets** :
   ```toml
   AF_AUTO_DATA = "1"
   S3_BUCKET = "…"
   AWS_REGION = "us-east-1"
   AWS_ACCESS_KEY_ID = "…"
   AWS_SECRET_ACCESS_KEY = "…"
   AWS_SESSION_TOKEN = "…"
   LLM_PROVIDER = "bedrock"
   AF_LANG = "fr"
   AF_VOICE_ENABLED = "0"   # "1" active la voix (Amazon Transcribe + Polly)
   ```
   Après la fermeture du compte AWS : `LLM_PROVIDER = "mock"` et retirer les clés; l'application rejoue les réponses
   enregistrées de Claude.
</details>

<details>
<summary><b>Données et sources</b></summary>

| Source | Contenu | Provenance |
|---|---|---|
| Jeu de départ (organisateurs) | 31 actifs, prix quotidiens 2021-11-12 → 2026-11-12, dividendes, USD/CAD, taux, IPC | Yahoo Finance, Banque du Canada, FRED (`Datathon2026Infos/alphaforge_starter/build_dataset.py`) |
| Avoirs des FNB | ce que les FNB détiennent réellement, pour compter une société une seule fois | fichiers des émetteurs (SPY au 2026-11-12) |
| Obligations | titres gouvernementaux canadiens et américains, détenus jusqu'à l'échéance | sources publiques datées (`data/README.md`) |

Tout est converti en CAD; rendements sur le cours ajusté. Limites : biais du survivant dans l'univers, avoirs = un
instantané. Sources, dates, traitement et conditions : [`data/README.md`](data/README.md).
</details>

<details>
<summary><b>Organisation du dépôt</b></summary>

```
interface/         interface guidée (vue client)
app/app.py         démonstration (vue du jury)
src/dh/agents/     profiler · market · portfolio · checks · guardian · critic · explainer · analyst · extractor
                   existing (portefeuille déjà détenu) · fixed_income · pipeline · trace · rules · scenarios
src/dh/            données, statistiques de risque, traces S3, Français ⇄ English (i18n)
aws/               architecture (français; anglais : *.en.md)
deliverables/      fiche d'une page, documentation technique, script vidéo (français; anglais : *.en.md)
cache/             réponses enregistrées de Claude (démonstration sans AWS)
notes/             conception, contrat entre agents, journal des décisions (notes de l'équipe, en anglais)
tests/             tests hors ligne
```
</details>

## Licence

MIT, voir [`LICENSE`](LICENSE).
