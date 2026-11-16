# Script vidéo — slides + démonstration du site (moins de 5 minutes)

Utiliser les **six slides fournies par l'équipe**, dans leur ordre : titre, Robert, architecture, validation,
limites, conclusion; et le site `https://alphaforge-ai-wj.streamlit.app/`. Les repères ci-dessous indiquent le support, l'écran
et l'élément à montrer. Ne pas remplacer la démonstration par une lecture des slides.

## Avant d'enregistrer

- Ouvrir les six slides fournies dans le navigateur et les préparer en plein écran. Garder leur ordre :
  **1 — AlphaForge AI; 2 — Robert; 3 — Architecture; 4 — Validation; 5 — Limites; 6 — Conclusion.**
  Sur la slide Limites, afficher « Objectif : 10 cas sur 100. Résultat du test : 19 cas sur 100.
  Le modèle doit être plus prudent. Amélioration testée, pas encore intégrée. »
- Préparer trois onglets du **site**, en français : **Robert avec Tesla**, **Amira**, **Robert avec un portefeuille existant**.
  Pour les deux premiers : **Votre profil** → ouvrir **Démarrez plus vite : un client fictif, ou décrivez-vous en quelques phrases**
  → **Clients fictifs** → choisir **Robert demande 25 % dans Tesla**, puis **Amira (26 ans, risque élevé, IA + crypto)**
  dans l'autre onglet → **L'utiliser** → **Lancer l'analyse**. Garder les résultats prêts.
- Pour le troisième : **Accueil** → **J'ai déjà un portefeuille** → **Essayer avec un client fictif** et
  **Essayer un portefeuille fictif (surtout canadien)** → lancer l'analyse.
- Dans l'onglet Amira, préparer la réponse de l'**Assistant** à « NVDA et QQQ, c'est le même pari ? ».
  Dans le troisième onglet, préparer « Et si j'ajoutais 40 000 $ de XSP à mon portefeuille actuel ? ».
  Envoyer ces questions avant l'enregistrement; vérifier les réponses et les outils cités.
- Préparer les réponses Bedrock avec `make warm` lorsque les accès AWS sont disponibles. Une réponse enregistrée
  reste une **relecture**, pas un nouvel appel en direct : laisser son indicateur de source visible.
- Vérifier les valeurs affichées avant de filmer. Les chiffres du script viennent de `results.csv` et de
  `deliverables/EVALUATION.md`, sur la fenêtre 2021–2026. Ne pas les lire devant des résultats d'une autre fenêtre.
- Enregistrer en 1920 × 1080 si possible. Slides en plein écran à 100 %; régler le zoom du site pour lire les cartes
  sans défilement horizontal. Couper les notifications. Ne pas filmer les clés AWS ni les réglages de secrets.

## Déroulé à enregistrer

| Temps | À l'écran — actions précises | Narration |
|---|---|---|
| **0:00–0:25 — Le problème** | **0:00–0:08 : slide 1, `title`**, titre AlphaForge AI. **0:08–0:25 : slide 2, `robert`**. Pointer « Retraite dans 4 ans », « Perte acceptée 15 % », puis la demande Tesla en rouge. | « Robert a 59 ans. Il prend sa retraite dans quatre ans et veut mettre 25 % de son épargne dans Tesla. Comment savoir si cette demande lui convient ? AlphaForge part de sa situation, vérifie ses limites et explique les options possibles. Le choix reste au client. » |
| **0:25–1:05 — Les agents et AWS** | **Slide 3, `archi`**, pendant toute cette séquence. **0:25–0:45 :** pointer les quatre cases vertes : Extracteur, Critique, Explicateur, Analyste. **0:45–0:55 :** pointer Profileur, Portefeuille, Gardien, puis la phrase du bas. **0:55–1:05 :** pointer **Amazon Bedrock**, puis **Amazon S3**, sur cette même slide. | « Quatre agents Strands utilisent Claude sur Amazon Bedrock. L'Extracteur lit les mots du client. Le Critique examine les propositions avec des outils. L'Explicateur rédige une réponse accessible. L'Analyste répond aux questions de suivi. Mais les agents ne fixent pas eux-mêmes les limites : le code les calcule et les vérifie. Les agents argumentent; le code fait respecter. Bedrock fait fonctionner les agents. S3 conserve les données et les traces des analyses, pour retrouver les calculs et les contrôles derrière une réponse. » |
| **1:05–1:50 — Robert sur le site** | **Quitter les slides → onglet du site « Robert avec Tesla »**. Menu **Vos résultats** → onglet **Vos options**. **1:05–1:20 :** cadrer « Vos limites, Robert » et la limite de 15 %. **1:20–1:50 :** descendre à **Le placement que vous avez demandé**; montrer la demande à 25 %, les limites dépassées et la version ajustée. Ne pas ouvrir les contrôles techniques. | « Voici le résultat pour Robert sur le site. Ses réponses donnent une limite de perte de 15 %. Or, dans les données utilisées, Tesla a déjà perdu 70,9 %. Avec un quart du portefeuille dans cette action, cette baisse aurait représenté 17,7 % de son épargne totale. Sa demande dépasse donc sa limite. AlphaForge le lui montre et calcule une part compatible avec les contrôles : ici, jusqu'à 3,1 %. Ce n'est ni une promesse de sécurité ni un ordre d'achat. C'est une comparaison qu'il peut comprendre. » |
| **1:50–2:35 — Les options et le Critique** | **1:50–2:15 : site, Vos résultats → Vos options**, revenir aux cartes. Cadrer la première option et **Comment votre argent est réparti** : noms, pourcentages, montants. Pointer 15 % en actions, la baisse historique et le résultat de 2022. **2:15–2:35 : menu Activité**, ouvrir le relais du **Critique vers le Portefeuille**; montrer une objection et le résultat d'outil qui l'appuie. | « Les options sont présentées avec les placements, leur poids et les montants en dollars. La première contient 15 % d'actions. Elle a perdu jusqu'à 8,6 % dans l'historique, et 5,8 % en 2022. Ce sont des observations, pas des prévisions. Le Critique examine ensuite ce qui pourrait poser problème : concentration, corrélations, poids d'un placement dans le risque total. Ses objections doivent s'appuyer sur des résultats d'outils. S'il propose un changement, le code recalcule le portefeuille et vérifie à nouveau les limites. » |
| **2:35–2:55 — Une explication lisible** | **Site, Vos résultats → En mots simples**. Cadrer un titre et un paragraphe court de l'explication française. Pointer un chiffre qui vient de la carte précédente. Garder visible la mention de source; ne pas dérouler la trace JSON. | « Robert reçoit une explication en mots simples. Les chiffres viennent des calculs : le modèle utilise des repères que le code remplace par les valeurs vérifiées. Si l'explication ne passe pas les contrôles, une version structurée la remplace. » |
| **2:55–3:25 — Un autre profil** | **Passer à l'onglet du site « Amira »**. **2:55–3:10 : Vos résultats → Vos options**, montrer son profil et sa répartition différente. **3:10–3:25 : menu Assistant**, afficher la réponse préparée à « NVDA et QQQ, c'est le même pari ? », puis ouvrir **Comment cela a été vérifié** pour montrer l'outil de corrélation. | « Avec Amira, les règles sont les mêmes, mais le résultat change. Elle est plus jeune, son horizon est plus long et elle accepte davantage de risque. Elle peut aussi poser une question précise : Nvidia et le fonds Nasdaq représentent-ils le même pari ? L'Analyste consulte les données de corrélation et explique le résultat, au lieu d'improviser une réponse. » |
| **3:25–4:05 — Le portefeuille déjà détenu** | **Passer à l'onglet du site « Robert avec un portefeuille existant »**. **3:25–3:45 : Vos résultats → Vos options**, descendre à **Le portefeuille que vous avez déjà**; cadrer le tableau des montants actuels, proposés et des écarts. **3:45–4:05 : menu Assistant**, afficher la réponse préparée sur l'ajout de XSP; pointer la mention du substitut et la source des contrôles. | « Le client peut aussi partir de son portefeuille actuel. AlphaForge examine ses placements, la concentration, les secteurs et les frais. Il compare ensuite ce portefeuille avec une option qui respecte les limites vérifiées, en montrant les différences en dollars. Lorsqu'un fonds manque dans les données, comme XSP, un substitut est clairement indiqué. Le client sait donc ce qui a été mesuré directement et ce qui repose sur une approximation. Les résultats et les contrôles sont conservés dans S3. » |
| **4:05–4:45 — Les tests et la limite actuelle** | **Retour aux slides. 4:05–4:20 : slide 4, `valid`**, pointer les quatre résultats, sans terminal animé. **4:20–4:45 : slide 5, `limits`**, pointer « 10 cas sur 100 », puis « 19 cas sur 100 », puis **pas encore intégrée**. Ces valeurs viennent de tests sur des marchés simulés, pas d'un rendement client ni d'une probabilité personnelle affichée par le site. | « Nous avons aussi testé le système : seize profils sur seize donnent le verdict attendu, deux cent dix-sept chiffres sont vérifiés, deux cents faux chiffres ajoutés par notre test sont détectés, et dix cas pièges sont traités comme prévu. Il reste une limite importante. Sur des marchés simulés, nous visions au plus dix cas sur cent où la perte acceptée est dépassée. Nous en observons dix-neuf. Le modèle doit donc être plus prudent. L'amélioration testée réduit la part en actions, mais elle n'est pas encore intégrée. » |
| **4:45–4:58 — Conclusion** | **Slide 6, `end`**. Laisser visibles les noms de l'équipe, le site et le dépôt. Finir sur cette slide, sans revenir au navigateur ou au terminal. | « AlphaForge aide à comprendre ce qui correspond à sa situation, avec des limites expliquées et des calculs vérifiables. Une simulation, pas un conseil en placement. Merci. » |

## Si l'enregistrement dépasse cinq minutes

Couper la question sur XSP et raccourcir la partie portefeuille existant. Garder les holdings à l'écran, les outils du
Critique, le rôle réel de Bedrock et de S3, ainsi que la limite du modèle de perte. Ne pas accélérer le passage « 10 / 19 ».

Les slides de validation présentent des résultats enregistrés, pas une commande exécutée en direct.
L'amélioration du modèle de perte est une piste testée et documentée; cette vidéo ne prétend pas qu'elle est déjà livrée.
