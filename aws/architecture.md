# Architecture : ce qui fonctionne aujourd'hui (15 novembre; décisions #14, #30, #40, #42, #46, #49)

**Des agents Strands pour les étapes qui décident, un pipeline fixe pour l'orchestration, des modèles sur Amazon
Bedrock, la trace de chaque exécution conservée dans Amazon S3.** Les deux applications Streamlit fonctionnent en
local et sur Streamlit Community Cloud, qui lit les données dans S3 au premier démarrage; une ligne de commande exécute
le même pipeline. Bedrock AgentCore Runtime était prévu et n'est **pas déployé**. « Les agents enquêtent et
argumentent, le code fait respecter. » Pointillés = non construit, non déployé ou facultatif.
Image : [`architecture.png`](architecture.png) · *English: [`architecture.en.md`](architecture.en.md)*

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 320, "nodeSpacing": 40, "rankSpacing": 50}}}%%
flowchart TB
    subgraph L0["0 · Entrée · app/ et interface/"]
        direction LR
        P0["Personas fictifs<br/>Amira · Mateo · Robert"]
        Q["Questions guidées<br/>vérifiées avec les limites du moteur"]
        VO["Voix, facultative<br/>parler, écouter la réponse"] --> T
        H["« J'ai déjà un portefeuille »<br/>placements ligne par ligne ou en mots"]
        T["Texte libre"] --> EXT["Extracteur · agent Strands<br/>outil : check_profile<br/>fait manquant → on demande, on ne devine pas"]
    end

    O{{"Orchestrateur · pipeline.py<br/>ordre fixe · une ronde · le Gardien s'exécute toujours"}}
    P0 --> O
    H --> O
    Q --> O
    EXT --> O

    subgraph CORE["Cœur déterministe · sans LLM"]
        direction TB
        PR["1 · Profileur<br/>tolérance · capacité · connaissances → limites, chacune avec sa raison<br/>limite de perte · plancher défensif · plafonds par société et crypto<br/>choix KYC → A : contre-vérification · question d'espérance"]
        MD["2 · Données de marché<br/>31 actifs en CAD · volatilité · pire baisse · CVaR · corrélations<br/>crise de 2022 · perspective d'objectif"]
        PF["3 · Portefeuille<br/>jusqu'à 3 stratégies = 3 niveaux de risque<br/>répartition calculée : plus grande part de croissance qui respecte la règle de perte simulée sur l'horizon,<br/>plafonnée par l'horizon, la liquidité, le filet de sécurité · dit laquelle a décidé<br/>crypto seulement si demandée + permise + appuyée par les données"]
        CK["Contrôles C–F<br/>sociétés et secteurs à travers les FNB · géographie ·<br/>doublons · baisse en % et en $ · objectif · adéquation au profil"]
        EXR["Revue d'un portefeuille déjà détenu<br/>mêmes contrôles C–F et Gardien · frais en $ ·<br/>substituts identifiés pour les fonds sans données ·<br/>reconstruction vers la première stratégie, mouvements en $"]
        FI["Recherche d'obligations<br/>préférence « obligations seulement » : titres gouvernementaux<br/>canadiens et américains sourcés, détenus jusqu'à l'échéance, flux en CAD<br/>aucune offre inventée, aucune garantie promise"]
        RQ["Demande côte à côte<br/>« telle que demandée » et « ce qui convient », mêmes contrôles<br/>avantages et inconvénients tirés des nombres"]
    end

    GU{{"Gardien · contrôles de perte et de cohérence<br/>calqués sur le Règlement 31-103 (KYC / convenance)<br/>✔ réussi · ⚠ à divulguer · ✘ bloque"}}

    subgraph AG["Agents Strands · outils plafonnés et tracés"]
        direction TB
        CR["4 · Critique<br/>enquête avant d'objecter · ≤ 6 appels d'outils<br/>≤ 3 objections, nombres appuyés par les outils ou les faits<br/>menu de corrections : fusionner · réduire · déplacer · divulguer"]
        EX["5 · Explicateur<br/>écrit des identifiants, jamais des nombres ({n7})<br/>s'autovérifie avec G11–G13"]
        AN["Analyste · questions de suivi<br/>les scénarios relancent tout le pipeline"]
    end

    TOOLS["Outils = fonctions déterministes, JSON en entrée et en sortie<br/>marché : asset_facts · portfolio_stats · stress_test · correlation_between ·<br/>goal_check · required_return · list_assets<br/>vues sur l'exécution : look_through · strategy_checks · limit_reason ·<br/>risk_contributions (covariance seulement, aucune prévision)<br/>Analyste seulement : what_if_position · what_if_profile (relancent le pipeline)"]

    O --> PR
    O -- "préférence obligations seulement" --> FI
    FI -- "correspondances ou « aucune correspondance appuyée », avec sources" --> UI
    PR -- "éléments essentiels manquants (G1)" --> ASK["On interroge le client"]
    PR --> MD --> PF --> CK --> GU
    GU -- "✘ stratégie retirée, raison dans la trace" --> DROP["Retirée"]
    GU -- "✔ / ⚠" --> CR
    CR -- "une correction par stratégie :<br/>resserrer une donnée, relancer tout le calcul" --> PF
    CR -- "objections non corrigées → inconvénients" --> RQ
    RQ --> EX
    PF -- "première stratégie = cible de reconstruction" --> EXR
    EXR -- "section « le portefeuille que vous avez déjà »" --> EX
    CR -. "le revoit aussi, divulgation seulement" .-> EXR
    EX --> GU2{{"Gardien G11–G13<br/>avertissement · chaque nombre tracé ·<br/>chaque demande expliquée"}}
    GU2 -- "✘ → gabarit déterministe, dit dans la trace" --> UI
    GU2 -- "✔" --> UI["Applications : limites et raisons · stratégies et graphiques ·<br/>explication · Analyste · trace · Français ⇄ English"]
    UI -- "question de suivi" --> AN
    AN -- "scénario → même pipeline, Gardien compris" --> O
    AN -- "réponse : chaque nombre vient d'un résultat d'outil cité, vérifié par le code" --> UI

    CR -. appelle .-> TOOLS
    AN -. appelle .-> TOOLS

    TR[("Trace · une ligne par relais<br/>appels d'outils · nombres · verdicts<br/>jamais le raisonnement brut du modèle")]
    O -. écrit .-> TR

    subgraph AWS["AWS (diapositive 7)"]
        BR["Amazon Bedrock<br/>Claude Opus 5.5 · us-east-1"]
        S3[("Amazon S3<br/>traces/ : un JSON par exécution<br/>raw/ : données et catalogue d'obligations de l'app hébergée<br/>voice/ : audio, supprimé une fois transcrit")]
        TP["Amazon Transcribe · Amazon Polly<br/>parole → texte · texte → parole<br/>facultatif (AF_VOICE_ENABLED)"]
        AC["Bedrock AgentCore Runtime<br/>prévu, NON déployé"]
    end
    AG -. "modèles" .-> BR
    EXT -. "modèle" .-> BR
    TR -- "chaque exécution (copie locale si S3 est inaccessible)" --> S3
    O -. "non déployé" .-> AC
    HOST["Streamlit Community Cloud<br/>les applications hébergées"]
    UI -. "hébergée sur" .-> HOST
    S3 -. "données raw/ au premier démarrage" .-> HOST
    VO -. "audio" .-> TP

    style AC stroke-dasharray: 5 5
    style TP stroke-dasharray: 5 5
    style O fill:#fde68a,stroke:#b45309,color:#000
    style GU fill:#fde68a,stroke:#b45309,color:#000
    style GU2 fill:#fde68a,stroke:#b45309,color:#000
    style CR fill:#dbeafe,stroke:#1d4ed8,color:#000
    style EX fill:#dbeafe,stroke:#1d4ed8,color:#000
    style AN fill:#dbeafe,stroke:#1d4ed8,color:#000
    style EXT fill:#dbeafe,stroke:#1d4ed8,color:#000
```

Jaune = là où le code décide (orchestrateur, Gardien). Bleu = agents Strands (ils décident quels outils appeler,
jamais une limite ni un nombre).

## Les couches en bref

| Couche | Question à laquelle elle répond | Construite avec |
|---|---|---|
| Orchestration | Dans quel ordre s'exécutent les étapes, que se passe-t-il sur un ✘ ? | `src/dh/agents/pipeline.py` : ordre fixe, une ronde du Critique, le Gardien ne peut pas être contourné. Un ✘ sur une stratégie la retire (raison dans la trace); un ✘ sur le texte le remplace par le gabarit |
| Agents qui décident | Quels outils appeler, et quand s'arrêter | **Strands Agents** sur Bedrock : Extracteur, Critique, Explicateur, Analyste. Appels plafonnés et tracés; réponses de démonstration enregistrées et versionnées (`cache/`) pour rejouer sans AWS |
| Étapes déterministes | Les nombres et les règles | Python ordinaire : Profileur, données de marché, Portefeuille, contrôles C–F, demande côte à côte, Gardien. Les agents les appellent comme outils |
| Modèle | Le LLM | **Amazon Bedrock** : `global.anthropic.claude-opus-5-5` (Claude Opus 5.5), us-east-1, texte et outils vérifiés le 2026-11-14 (`make bedrock-check`) |
| Hébergement | Où s'exécute le pipeline | **Streamlit Community Cloud** (applications hébergées) et **en local** (`make app`, `make ui`, ligne de commande). Données tirées de `s3://$S3_BUCKET/raw/` au premier démarrage. Bedrock AgentCore Runtime : **non déployé** |
| Traces et données | Où sont conservées les exécutions et les données | **Amazon S3** : `traces/` chaque exécution des deux applications et de la ligne de commande (copie locale si S3 est inaccessible); `raw/` les données de l'application hébergée; `voice/` l'audio à transcrire, supprimé ensuite |
| Voix (facultative) | Parler au lieu de taper | **Amazon Transcribe** (parole → texte, français ou anglais du Canada) et **Amazon Polly** (réponse lue à voix haute), dans l'interface guidée, désactivée sauf si `AF_VOICE_ENABLED=1` |
| Langue | Français ou anglais | Bouton Français ⇄ English dans les deux applications, français par défaut (`AF_LANG`) : interface, textes du moteur (traduits à l'affichage, nombres intacts) et textes de Claude (rédigés directement en français), #49 |

| Composant | LLM ? | Résultat |
|---|---|---|
| Extracteur | oui (Strands, outil `check_profile`) | champs du `profile` à partir du texte libre; questions de suivi pour ce qui manque; le code vérifie chaque champ (#29) |
| Profileur | non | `limits` : niveau de risque, limite de perte, planchers, plafonds par société et crypto, chacun avec sa raison; contre-vérification KYC (#40) |
| Données de marché | non | faits par actif, `strategy_stats`, périodes de crise, perspective d'objectif (Joud) |
| Portefeuille | non | jusqu'à 3 stratégies = 3 niveaux de risque (#32); plafond de croissance = plus grande part dont la probabilité simulée d'une baisse plus forte que la limite de perte sur l'horizon est ≤ 10 % (#46), plafonnée par la règle d'horizon, les retraits et le filet de sécurité; dit ce qui a décidé (#33) |
| Contrôles C–F | non | même forme pour chaque contrôle : valeur, limite, statut, raison, source (#20) |
| Gardien | non | ✔ / ⚠ / ✘ par règle sur chaque stratégie (17 règles : G1–G16 et G18; G7 = probabilité simulée d'une baisse plus forte que la limite de perte sur l'horizon ≤ 10 %, G18 = chaque nombre décrit les pondérations finales, #46); G11–G13 sur le texte |
| Critique | oui (Strands, 11 outils) | ≤ 3 objections, chaque nombre appuyé par un résultat d'outil cité ou par les faits reçus (#45); une correction par stratégie qui relance tout le calcul, revérifiée par le Gardien, l'original conservé en cas d'échec (#30) |
| Recherche d'obligations | non | pour une préférence « obligations seulement » : titres gouvernementaux canadiens et américains sourcés, détenus jusqu'à l'échéance (taux, échéance, flux en CAD); références publiques, pas des offres de courtiers; dit quand rien ne correspond |
| Demande côte à côte | non | la demande du client « telle que demandée » et « ce qui convient », mêmes contrôles; avantages et inconvénients tirés des nombres (#28) |
| Explicateur | oui (Strands, outil `check_text`) | texte au client avec des identifiants de nombres remplis par le code (G12 strict, #27); gabarit si un contrôle échoue (#23) |
| Revue d'un portefeuille déjà détenu | non (+ Critique, Explicateur, Analyste) | ce que le client détient, avec les mêmes contrôles C–F et le Gardien, les frais en $, des substituts identifiés et les mouvements en $ vers la première stratégie (#42, #44) |
| Analyste | oui (Strands, outils) | réponses aux questions de suivi; les scénarios relancent le pipeline, Gardien compris; chaque nombre vient d'un résultat d'outil cité (#35) |

**Hors de la démonstration :** l'optimiseur de Markowitz (branche `optimisation-markowitz`, Joud) a été testé et
écarté (#37) : avec des rendements moyens historiques, ses pondérations changeaient avec la période et ont perdu contre
l'équipondération hors échantillon. Ce qui ne dépend pas des rendements moyens est utilisé : les contributions au
risque (outil du Critique) et les choix KYC (contre-vérification du Profileur), #40.

Pourquoi ne pas laisser un agent orchestrer : un agent superviseur qui choisit l'étape suivante paraît plus agentique,
mais rien ne garantirait que le Gardien s'exécute à chaque fois, et les 16 scénarios de test ne seraient plus fiables
(`notes/decisions.md` #14).
