# Script vidéo (≤ 5 minutes, énoncé p. 15)

Deux clients contrastés (énoncé p. 15) : **Robert** (59 ans, prudent, demande 25 % dans Tesla) et **Amira** (26 ans,
risque élevé, IA et crypto), tous deux dans l'application de démonstration où les relais des agents sont visibles;
puis l'interface guidée qui revoit un portefeuille déjà détenu. Montrer AWS qui fait un vrai travail (diapositive 7 :
condition d'admissibilité). Environ 700 mots lus : ~4 min 45 à un rythme posé, 15 s de marge. Chaque réponse d'agent
montrée est une réponse que `make warm` a enregistrée (Bedrock rejoué, aucun appel en direct nécessaire).

**Nombres dits à voix haute** (règle 3, tous dans `results.csv`) : pire baisse de Tesla −70,9 %, 25 % à elle seule
−17,7 %, entre dans les limites jusqu'à 3,1 % (`persona-request`); limite de perte de Robert 15 % (`persona-limits`);
première stratégie 15 % en actions, pire baisse −8,6 %, 2022 −5,8 % (`persona-strategies`); 16 profils de test sur 16
(`guardian-scenarios`). Tout le reste : laisser l'écran le montrer, ne pas le dire.

## Avant d'enregistrer

1. `make warm` avec des clés AWS valides, puis versionner `cache/` (la démonstration rejoue les vraies réponses
   Bedrock; sans cela, les textes basculent vers le gabarit et le Critique vers sa version à règles).
2. Application de démonstration (`make app`, interface en **Français**) : lancer une fois « Robert demande 25 % dans
   Tesla » et « Amira ». Interface guidée (`make ui`) : Accueil → « J'ai déjà un portefeuille » → « Essayer avec un
   client fictif » + « Essayer un portefeuille fictif (surtout canadien) ». C'est exactement ce que `make warm` a
   enregistré; un autre client ou une autre question s'exécuterait en direct (ou basculerait).
3. Pour les questions de suivi, **cliquer sur les boutons de suggestion** (affichés en français) : ils envoient la
   question enregistrée. Une question tapée à la main n'aurait pas de réponse enregistrée.
4. À l'écran, l'interface est en français; les textes rédigés par les agents (explication, objections, réponses de
   l'Analyste) restent en anglais, comme indiqué dans la barre latérale. La narration les résume en français.
5. Navigateur à 125 %, une seule fenêtre, notifications coupées. Garder `aws/architecture.png` ouvert dans un
   onglet. Facultatif : la console S3 sur `traces/` pour la séquence de 3 min 35.

## Script

| Temps | À l'écran | Narration (lire tel quel) |
|---|---|---|
| **0:00–0:25** · Problème | Carton titre : « AlphaForge AI — un analyste en placement qui sait dire non, et montre pourquoi ». Puis la fiche de Robert. | « Les investisseurs voient tous les prix, mais pas ce qu'un portefeuille signifie pour eux : combien ils peuvent perdre, de combien de temps ils disposent, si une action à la mode leur convient. Voici Robert. Il a 59 ans, prend sa retraite dans quatre ans, et veut mettre 25 % de son épargne dans Tesla. Un bon conseiller ne dirait pas simplement oui, ou non. Il lui montrerait pourquoi. » |
| **0:25–1:05** · Architecture | `aws/architecture.png`. Pointer chaque boîte en la nommant : Extracteur, Profileur, Portefeuille, Gardien, Critique, Explicateur, Analyste; puis la boîte AWS. | « AlphaForge, c'est une équipe d'agents spécialisés, dans un ordre fixe. Quatre d'entre eux sont des agents Strands qui font tourner Claude sur Amazon Bedrock : l'Extracteur lit les mots du client, le Critique conteste les propositions, l'Explicateur rédige la réponse, et l'Analyste répond aux questions de suivi. Ils décident quoi vérifier et comment le dire. Mais chaque limite et chaque nombre viennent du code : le Profileur, le Portefeuille et le Gardien, dix-sept règles calquées sur les obligations canadiennes de connaissance du client. Les agents argumentent; le code fait respecter. Et chaque exécution est enregistrée dans Amazon S3, pour que toute réponse puisse être auditée. » |
| **1:05–1:50** · Les limites de Robert | Démonstration, « Robert demande 25 % dans Tesla ». Onglet **Profil et limites** : faire défiler les raisons du Profileur; s'arrêter sur la demande Tesla. | « Voici Robert. Le Profileur transforme ses réponses en limites, chacune avec sa raison. Sa limite de perte est de 15 % : la plus prudente entre ce qu'il nous a dit et ce que sa situation permet. Maintenant, sa demande. La pire baisse de Tesla dans les données a été de moins 70,9 %. À 25 %, Tesla à elle seule aurait coûté 17,7 % de tout son portefeuille, plus que toute sa limite de perte. Alors le système ne le refuse pas. Il lui dit que Tesla entre dans ses limites jusqu'à 3,1 %, et le choix lui appartient. » |
| **1:50–2:35** · Stratégies et Critique | Onglet **Stratégies** : la carte de la première stratégie (répartition, pire baisse, ce qui a fixé la répartition). Puis onglet **Activité et preuves** : défiler jusqu'à « Critic → Portfolio ». | « Le Portefeuille propose jusqu'à trois stratégies à des niveaux de risque différents. La première détient 15 % en actions. Sa pire baisse historique a été de 8,6 %, et en 2022 elle a perdu 5,8 %. Le portefeuille final passe aussi un contrôle de perte simulé, fondé sur des hypothèses déclarées, pas une garantie pour l'avenir. La carte dit ce qui a fixé cette répartition : ici, son horizon de quatre ans. Puis le Critique entre en jeu. Il ne donne pas qu'une opinion : il appelle d'abord des outils, les corrélations, la part de risque de chaque placement, les contrôles les plus près de leur limite, et chaque objection doit citer un résultat qu'il a obtenu. S'il propose une correction, le code recalcule toute la stratégie et le Gardien la vérifie de nouveau. » |
| **2:35–3:05** · Explication | Onglet **Explication** : le texte, puis les contrôles G11–G13 en dessous. | « L'Explicateur écrit pour Robert, en mots simples. Il ne tape jamais un nombre lui-même : il écrit des repères, et le code y insère les valeurs calculées. Le Gardien vérifie ensuite le texte : l'avertissement est là, chaque nombre est tracé, et sa demande Tesla reçoit une réponse. Si le texte échoue, un gabarit le remplace, et la trace dit pourquoi. » |
| **3:05–3:35** · Amira | Démonstration, « Amira » : **Profil et limites** (ses limites et raisons), **Stratégies** (la première carte), puis **Questions de suivi (Analyste)** : cliquer la suggestion « NVDA et QQQ, c'est le même pari ? ». | « Maintenant, une cliente très différente. Amira a 26 ans, quinze ans devant elle, et s'intéresse à l'IA et à la crypto. Même moteur, limites différentes, donc une réponse différente et justifiée : plus de place pour la croissance. La crypto n'est même envisagée que parce qu'elle l'a demandée, et elle ne reste que si son profil le permet et que les données sont d'accord; la trace dit laquelle des deux. Elle peut poser des questions de suivi, en français : l'Analyste vérifie si Nvidia et le FNB du Nasdaq sont le même pari en appelant l'outil de corrélation, et chaque nombre de sa réponse doit venir de cet outil. » |
| **3:35–4:20** · Portefeuille déjà détenu | Interface guidée : Accueil → « J'ai déjà un portefeuille » → client fictif + portefeuille fictif → **Vos résultats** : « Le portefeuille que vous avez déjà » (contrôles, frais, mouvements de reconstruction en $). Puis **Assistant** : cliquer la suggestion « Et si j'ajoutais 40 000 $ de XSP à mon portefeuille actuel ? ». Facultatif : console S3, le JSON de l'exécution dans `traces/`. | « Beaucoup de clients ne partent pas de zéro. Dans l'interface guidée, un client entre ce qu'il détient déjà, ou le décrit dans ses mots. Les mêmes contrôles et le même Gardien le revoient : concentration, secteurs, géographie, frais. Puis le système montre comment le reconstruire en une stratégie qui respecte ses limites, chaque mouvement en dollars. Posez une question sur un fonds dont nous n'avons pas les données, comme XSP, et il est mesuré avec un substitut identifié, jamais en silence. Et cette exécution, comme toutes les autres, est enregistrée dans Amazon S3. » |
| **4:20–4:40** · Validation, limites | Terminal : `make scenarios` qui se termine par « 16/16 ». Puis la liste des limites de la documentation technique. | « Nous le validons avec seize profils de test, dont des pièges voulus, comme une explication avec un nombre inventé. Les seize obtiennent le bon verdict. Et nous sommes clairs sur les limites : ces nombres décrivent le passé, pas l'avenir, et c'est une simulation, pas un conseil. » |
| **4:40–4:55** · Conclusion | Carton titre + noms de l'équipe + lien du dépôt. | « AlphaForge : un analyste qui s'adapte à chaque investisseur, dit non quand il le faut, et montre toujours pourquoi. Merci. » |

## À couper si c'est trop long

1. Retirer la séquence de la console S3 (3 min 35) : la phrase seule suffit.
2. Réduire la partie Explication (2 min 35) à ses deux premières phrases.
3. Ne jamais couper : les nombres de Tesla pour Robert, les appels d'outils du Critique, « les agents argumentent;
   le code fait respecter », les phrases sur AWS.

Enregistrer une première version, la regarder une fois, la refaire une fois. Téléverser sur Google Drive (lien
partagé « tous les utilisateurs disposant du lien »), envoyer lundi avant 14 h à logiciel@polyfinances.ca, objet
« Datathon - Équipe XX ».
