# AlphaForge AI

## Investissez selon vos propres limites, et comprenez pourquoi.

William Caron-Bastarache · Joud Katbe · Datathon PolyFinances 2026 · Banque Nationale × AWS

[alphaforge-ai-wj.streamlit.app](https://alphaforge-ai-wj.streamlit.app/) · [github.com/will13cb/alphaforge-ai](https://github.com/will13cb/alphaforge-ai)

### Le problème, en une situation
Robert prépare sa retraite dans quatre ans. Il veut placer **25 % de son épargne dans Tesla**, alors qu’il accepte une perte maximale de **15 %**. La chute historique de Tesla (**−70,9 %**) aurait représenté **−17,7 % de son portefeuille pour cette seule position**. AlphaForge explique le conflit et affiche un plafond calculé de **3,1 %**, sous les hypothèses du modèle. Le client garde la décision; aucune transaction n’est effectuée.

### Une réponse que le client peut examiner
Le client décrit sa situation en **français ou en anglais**, répond au questionnaire ou saisit ses placements actuels. L’application compare **jusqu’à trois options** avec les investissements, leurs poids et les montants en CAD. Elle explique les limites, les compromis et les résultats historiques. L’Assistant répond aux questions et recalcule les scénarios « et si ». Le portefeuille existant peut être analysé et comparé aux options proposées.

### Des agents qui enquêtent, du code qui vérifie
Quatre agents Strands : l’**Extracteur** structure le texte; le **Critique** enquête avec des outils; l’**Explicateur** présente les résultats; l’**Analyste** répond aux suivis. Le code calcule les limites et les répartitions. Le **Gardien** applique les contrôles. Une modification du Critique est recalculée et revérifiée. Les chiffres de l’explication sont insérés par le code; les réponses et leurs sources restent consultables. Les données manquantes sur les avoirs des FNB sont signalées.

### AWS, avec un rôle concret
**Amazon Bedrock** exécute les agents, avec le **Strands Agents SDK** pour leurs outils. **Amazon S3** fournit les données et reçoit les traces d’analyse; un enregistrement local prend le relais s’il est indisponible. **Transcribe** et **Polly** ajoutent la dictée et la lecture neuronale facultatives. L’application est hébergée sur **Streamlit Community Cloud**, hors AWS. Les réponses en direct, enregistrées ou de secours sont distinguées. **AgentCore Runtime n’est pas déployé.**

### Des données et des résultats vérifiables
Base de marché : **31 actifs, du 12 novembre 2021 au 12 novembre 2026**, prix Yahoo Finance du jeu des organisateurs, change et taux Banque du Canada; rendements en CAD. Un rejeu séparé de mars 2020 teste les mêmes poids hors de cette période. Le parcours obligations à échéance utilise un catalogue Canada–États-Unis sourcé; prix et disponibilité doivent être confirmés.

Évaluation hors ligne documentée : **16/16 profils**, **217/217 chiffres vérifiés** dans les textes du gabarit, **200/200 faux chiffres volontairement injectés détectés**, **10/10 cas pièges**. Ces résultats testent les contrôles; ils ne mesurent pas un rendement futur.

### Une limite assumée
Sur les marchés synthétiques du test de calibrage, la perte acceptée est dépassée dans **19 cas sur 100**, contre une cible de **10**. Le modèle doit être plus prudent. Une amélioration réduisant la part en actions a été testée, **sans être intégrée**. Les scénarios, les données disponibles et les hypothèses limitent la portée des résultats.

*Simulation pour profils fictifs · Aucun conseil en placement · Aucune transaction réelle.*

*Preuves : results.csv · deliverables/EVALUATION.md · Source de cette fiche : alphaforge-ai/main, c172b92.*
