# AlphaForge AI — un analyste en placement qui sait dire non, et montre pourquoi

William Caron-Bastarache · Joud Katbe · Datathon PolyFinances 2026 · Défi de la Banque Nationale × AWS

Simulation seulement, profils fictifs, pas un conseil financier. Application : https://alphaforge-ai-wj.streamlit.app/

**Problème.** Les investisseurs voient tous les prix, mais pas ce qu'un portefeuille signifie *pour eux* : combien ils
peuvent perdre, de combien de temps ils disposent, si une action à la mode leur convient. Un homme prudent de 59 ans
qui demande 25 % dans Tesla mérite une réponse claire avec ses propres chiffres, pas une cote de risque générique ni
un « oui » discret.

**Approche agentique.** Des agents spécialisés dans un ordre fixe, pour que les contrôles s'exécutent toujours :
**Extracteur** (agent : les mots du client → profil; chaque nombre doit figurer dans son texte) → **Profileur** (les
limites du client, chacune avec sa raison écrite) → **Données de marché** (faits de risque par actif) →
**Portefeuille** (jusqu'à 3 stratégies à des niveaux de risque différents) → **Gardien** (contrôles de perte, de
diversification et de cohérence; un ✘ retire la stratégie) → **Critique** (agent : enquête avec 11 outils avant
d'objecter; chaque objection doit citer un résultat d'outil, et sa correction, une par stratégie, est recalculée par
le code et revérifiée) → **Explicateur** (agent : rédige la réponse et vérifie sa propre ébauche avec les règles du
Gardien) → **Gardien** de nouveau sur le texte → **Analyste** (agent : questions de suivi, ses scénarios relancent
tout le pipeline). Les agents choisissent quoi vérifier et comment le dire; *le code fixe chaque limite et chaque
nombre.*

**Ce qui est original.**

- **Les limites suivent le client et les données, pas une table fixe, et disent d'où elles viennent.** La
  répartition actions / obligations est la plus stricte d'une règle d'horizon (un jugement assumé), de l'argent requis
  d'ici 3 ans, et de la plus grande part dont la probabilité simulée de dépasser le seuil de perte sur l'horizon reste
  sous un seuil de modèle déclaré; la trace nomme celle qui a décidé. Trois stratégies = trois niveaux de risque; le
  client choisit. Le plafond d'une société vient de sa propre pire baisse : pour Robert, Tesla a chuté de −70,9 %,
  donc 25 % à elle seule aurait coûté −17,7 % du portefeuille, plus que toute sa limite de perte de 15 %; elle entre
  dans ses limites jusqu'à 3,1 %. La réponse lui donne ces chiffres; le choix lui appartient.
- **Transparence des FNB :** une société détenue directement *et* à travers des FNB est comptée une seule fois, pour vrai.
- **Chaque nombre est tracé :** le Gardien rejette toute explication qui cite un % que le pipeline n'a pas calculé;
  les nombres du Critique et de l'Analyste doivent venir des résultats d'outils qu'ils citent.
- **Testé, puis écarté :** un optimiseur moyenne-variance (ses pondérations changeaient avec la période); nous ne
  gardons que ce qui décrit le risque sans prévoir (la part de risque de chaque placement).

La simulation de perte utilise l'encaisse plus une prime annuelle de 3 % sur les actifs de croissance (hypothèse de
l'équipe), un seuil de dépassement de 10 % et une sensibilité divulguée. Ce n'est pas une garantie des pertes futures.

**Sources de données.** Jeu de départ des organisateurs : prix quotidiens de 31 actifs, 2021-11-12 → 2026-11-12 (Yahoo
Finance), USD/CAD et taux (Banque du Canada), macro américaine (FRED); tous les rendements en CAD. Avoirs des FNB
publiés par l'émetteur (SPY de State Street, au 2026-11-12) pour la transparence. Sources, traitement et limites
documentés dans `data/README.md`.

**Explicabilité.** Chaque limite porte sa raison (« horizon de 4 ans → au plus 15 % en actions »); chaque stratégie, sa
pire baisse, son comportement en 2022 et sa probabilité de perte (vue « risque seulement », pas une prévision); chaque
relais entre agents est inscrit dans une trace d'étapes, de nombres et de verdicts, jamais le raisonnement brut du modèle.

**AWS (condition d'admissibilité, chaque service avec un vrai rôle).** **Amazon Bedrock** exécute Claude Opus 5.5 pour
les quatre agents; le **Strands Agents SDK** leur donne leurs outils et leur boucle d'outils; **Amazon S3** conserve
les preuves de chaque exécution en JSON (`traces/`), pour que toute réponse puisse être auditée après coup; la voix
facultative utilise **Amazon Transcribe** et **Polly**.

**Validé.** 16 profils de test (les trois personas + des pièges : un débutant qui veut 100 % de bitcoin, un horizon de
2 ans avec un fort appétit pour le risque, une explication avec un nombre inventé…) → 16/16 verdicts corrects (`results.csv`).

**Avantages pour l'utilisateur.**

- Voit ce qui respecte *ses* limites, dans ses chiffres (% et $), avant de décider.
- Reçoit un respectueux « voici ce que cela vous coûterait » plutôt qu'un oui silencieux ou un non sec.
- Peut vérifier chaque affirmation : sources, hypothèses et limites sont montrées avec le résultat.
- Peut partir du portefeuille qu'il détient déjà : mêmes contrôles, frais en $, et les mouvements vers une stratégie qui convient.
- Deux vues du même moteur, en français ou en anglais : une interface guidée (au clavier ou à la voix) et une vue de démonstration avec chaque relais.
