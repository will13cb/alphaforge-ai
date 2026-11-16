# AlphaForge AI : architecture AWS

L’application **Streamlit est hébergée hors AWS**. Son processus Python orchestre les agents avec le SDK
**Strands**, appelle **Amazon Bedrock** pour les tâches de langage, et utilise **Amazon S3** pour les données et
les traces. **Amazon Transcribe** et **Amazon Polly** ajoutent une assistance vocale facultative. Les calculs
financiers et les règles restent dans le code déterministe de l’application.

Les clients AWS utilisent `AWS_REGION`, avec **`us-east-1` par défaut**. Le modèle par défaut est le profil
d’inférence **global** `global.anthropic.claude-opus-5-5` : la région du client ne garantit donc pas que toute
l’inférence y reste. Le modèle peut être remplacé par configuration. **AgentCore Runtime n’est pas déployé** :
`src/dh/agents/pipeline.py` orchestre les étapes dans l’hôte Streamlit.

[SVG](AWS_ARCHITECTURE.svg) · [PNG](AWS_ARCHITECTURE.png) · [English](AWS_ARCHITECTURE.en.md) ·
[Architecture des agents](architecture.md). Images générées par `scripts/build_aws_diagram.py`.

![Architecture AWS d’AlphaForge AI](AWS_ARCHITECTURE.svg)

## Services et échanges réels

| Composant | Fonction et données | Opérations et déclenchement |
|---|---|---|
| **Amazon Bedrock** | Quatre agents Strands : **Extracteur** (texte → faits), **Critique** (outils et objections), **Explicateur** (texte à partir de faits vérifiés), **Analyste** (questions et simulations « et si »). Les outils déterministes exécutent les calculs. | `bedrock-runtime` **Converse / ConverseStream** via `BedrockModel`; mode `LLM_PROVIDER=bedrock` et absence de cache correspondant utilisable. Le formulaire guidé ne nécessite pas l’Extracteur. |
| **Strands Agents SDK** | Bibliothèque Python dans l’application : boucle d’agent et outils structurés, pas un service d’hébergement. | Appels Bedrock et fonctions Python locales; outils propres à chaque agent. |
| **S3 `raw/`** | Prix, change, taux, avoirs des FNB; catalogues et fondamentaux supplémentaires si configurés. Copie locale dans `data/raw/`. | `GetObject` via `download_file` si les fichiers requis manquent et `AF_AUTO_DATA=1`. `make data-up` publie les fichiers préparés via `upload_file`. |
| **S3 `raw/fixed_income/`** | `instruments.csv`, `reference_snapshot.json`, `sources_metadata.csv`, `quality_report.csv` : instruments, contexte daté / change, sources et rejets. | `ensure_fixed_income()` tente un chargement indépendant si le catalogue local manque, avec `AF_AUTO_DATA=1` et `S3_BUCKET`; aucune reconstruction des prix historiques requise. |
| **S3 `traces/YYYY-MM-DD/<run_id>.json`** | Profil, limites, stratégies ou scénario obligataire, contrôles, explication et échanges observables. Les suivis peuvent référencer l’exécution précédente; aucun raisonnement interne brut du modèle. | `PutObject` lors de l’enregistrement d’une analyse ou d’un suivi; repli local en cas d’échec. |
| **S3 `voice/<uuid>/`** | `input.wav` et `transcript.json`, tampon temporaire de dictée. Le téléversement audio demande le chiffrement serveur `AES256`. | `PutObject`, `GetObject`, `DeleteObject` pour une dictée explicitement envoyée; nettoyage tenté après lecture, annulation ou erreur terminale. |
| **Amazon Transcribe** | Transcription **par lot** d’un enregistrement court, `fr-CA` ou `en-CA`; texte à relire avant soumission au moteur financier. | `StartTranscriptionJob`, `GetTranscriptionJob`, `DeleteTranscriptionJob`; nécessite `AF_VOICE_ENABLED=1`, stockage et permissions. Ce n’est pas une conversation en continu. |
| **Amazon Polly** | Lecture du texte affiché, sans réécriture financière; moteur **neural**, Gabrielle en français canadien et Joanna en anglais. Audio en mémoire de session. | `SynthesizeSpeech` à la demande : MP3 pour un passage court; passages PCM assemblés en WAV pour un texte long. Indépendant de `LLM_PROVIDER`. |
| **AWS STS** | Diagnostic des identifiants configurés. | `GetCallerIdentity` dans `make bedrock-check`; pas une étape de chaque analyse. |

## Deux parcours financiers distincts

**Portefeuille de marché.** Le formulaire fournit les faits; un texte libre peut passer par l’Extracteur. Le
Profiler calcule les limites, les données de marché alimentent les mesures et Portfolio propose jusqu’à trois
stratégies. Les contrôles déterministes et le Gardien filtrent les résultats. Le Critique peut demander des
vérifications et une révision qui relance calculs et contrôles. L’Explicateur utilise les faits calculés et des
repères numériques remplis par le code; les vérifications peuvent remplacer son texte par un gabarit. L’Analyste
choisit des outils pour les suivis; seuls les outils de scénario relancent le pipeline.

**Obligations détenues jusqu’à l’échéance (`fixed_rate`).** Une branche séparée recherche un instrument dans le
catalogue Canada / États-Unis et calcule les flux sous les hypothèses affichées. Elle **ne passe pas par** les
stratégies de marché, leur Gardien, le Critique ni l’Explicateur Bedrock. Le résultat est un scénario avec
avertissement / devis à confirmer, ou une absence de correspondance, pas une approbation par les contrôles de
portefeuille. L’explication est déterministe. Sans catalogue local, `bond_rates.py` consulte les sources publiques
(Banque du Canada, TreasuryDirect); un instantané daté est utilisé si disponible lors d’un échec. Taux de référence
et résultats d’enchères ne sont pas des offres exécutables.

## Modes et défaillances visibles

- `LLM_PROVIDER=mock` est le mode hors ligne par défaut. Des entrées correspondantes dans `cache/` et `.cache/`
  peuvent aussi éviter Bedrock en mode connecté. Une réponse enregistrée ne prouve pas une connexion AWS actuelle.
  `make warm` prépare des réponses; `make backup` peut exporter les traces. Ces commandes ne sont pas automatiques.
- L’Extracteur accepte les faits explicites en français et en anglais, y compris les nombres français. Le quiz
  facultatif est conservé seulement si les réponses sont écrites et valides. Une erreur Bedrock déclenche le parseur
  local; des faits explicites peuvent compléter une extraction de modèle ou de cache. Le résultat expose `source`,
  `failure_type` et `supplemented_fields`; l’écran du profil distingue modèle, cache et parseur.
- Critique, Explicateur et Analyste ont des replis déterministes, aux capacités limitées pour les questions libres.
  Leurs sources et notes figurent dans les résultats / traces; une configuration « live » seule ne décrit pas
  l’origine réelle de chaque réponse.
- Si S3 est absent ou inaccessible, `tracestore` tente `outputs/traces/`. Si l’écriture locale échoue aussi,
  l’application peut continuer **sans trace persistée** : le chemin sûr marque `stored="none"`; le service de
  l’interface intercepte et journalise aussi les erreurs d’enregistrement. La persistance n’est pas garantie.
- Sans données de marché locales, le démarrage autorisé tente S3 puis une reconstruction depuis les sources
  publiques. Un échec peut rendre l’analyse de marché indisponible; le mode obligataire a son propre chemin de données.

## Conservation et configuration

Les identifiants sont configurés hors du dépôt, via les secrets de l’hôte ou la chaîne d’identifiants AWS; `.env`
n’est pas versionné. `S3_BUCKET`, les permissions S3 / Bedrock / voix et, au besoin, un jeton de session valide
restent des prérequis d’exploitation. Ce document décrit le code, pas la disponibilité actuelle de ces accès.

L’application est destinée aux **profils fictifs**, sans transaction ni conseil financier personnalisé. Les textes
et profils saisis peuvent figurer dans les traces; le code ne constitue pas un mécanisme d’anonymisation. Les
sources et limites des fichiers publics figurent dans [`data/README.md`](../data/README.md).

La suppression des objets vocaux et des métadonnées de tâche est **best effort**. Une tâche Transcribe en cours ne
peut pas être arrêtée et peut écrire après une annulation. Configurer une règle S3 expirant **uniquement `voice/`
après un jour** pour les sessions abandonnées, pannes et nettoyages échoués; le code ne l’installe pas. Des tâches
terminées peuvent nécessiter un nettoyage opérateur. Les transcriptions confirmées suivent la conservation normale
des textes et traces. Voir [`voice-accessibility.md`](voice-accessibility.md) pour les permissions et le parcours vocal.
