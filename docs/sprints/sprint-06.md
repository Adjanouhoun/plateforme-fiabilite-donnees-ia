# Sprint 6 — Assistance IA contrôlée

## Statut

État des lieux ouvert. Aucun appel à un modèle ni aucune dépendance IA n'est
implémenté.

## Objectif issu de la feuille de route

Produire une explication d'incident à partir des faits enregistrés sans déléguer
à l'IA les décisions de qualité ou de publication.

## État des lieux au 23 juillet 2026

### Faits déjà disponibles

- identité, état, sévérité et chronologie de l'incident ;
- contrôle déclencheur, règle attendue, valeur observée et preuve technique ;
- pipeline, propriétaire, environnement et criticité ;
- actif déclencheur et actifs aval issus du lineage prouvé ;
- impact métier qualifié comme mesuré, déclaré ou inconnu ;
- historique des événements de l'incident.

### Frontières déjà imposées par le projet

- les contrôles déterministes restent seuls responsables du statut de qualité ;
- une explication IA ne peut ni modifier un statut, ni fermer un incident, ni
  déclencher une remédiation ;
- les faits mesurés doivent rester visuellement distincts du texte généré ;
- l'absence de donnée ne doit pas être comblée par une invention ;
- le service doit avoir un comportement explicite lorsqu'il est indisponible ;
- le protocole d'évaluation doit être versionné.

### Éléments absents

- durée de conservation des requêtes et réponses ;
- format de sortie contractuel ;
- critères d'évaluation acceptés ;
- secrets d'accès au service IA.

## Décision fournisseur validée

- fournisseur : Google Gemini API ;
- palier visé : Free Tier pour le POC ;
- aucune bascule automatique vers une offre payante ;
- modèle initial validé : `gemini-3.5-flash-lite` ;
- le nom du modèle reste configurable afin de pouvoir changer de version sans
  modifier le modèle commun ni l'interface Streamlit ;
- l'intégration restera derrière une interface interne afin de ne pas coupler le
  modèle commun ni Streamlit au SDK Gemini.

## Politique de données et d'audit validée

- seuls les faits strictement nécessaires et assainis peuvent être transmis à
  Gemini ;
- les secrets, données personnelles, chaînes de connexion et messages d'erreur
  bruts sont exclus avant tout appel externe ;
- chaque explication générée est conservée dans PostgreSQL avec le modèle, la
  date de génération et les références factuelles utilisées ;
- cette conservation sert l'audit et ne donne aucun pouvoir décisionnel au
  modèle.

## Périmètre minimal proposé

1. Construire un paquet factuel structuré depuis le modèle commun.
2. Exclure les secrets, messages bruts et champs non nécessaires.
3. Demander au modèle une explication structurée : résumé, faits utilisés,
   inconnues, pistes de diagnostic et niveau de confiance déclaré.
4. Refuser toute réponse qui ne respecte pas le schéma attendu.
5. Afficher la réponse comme contenu généré, avec le modèle et la date.
6. Conserver un mode dégradé déterministe lorsque le service est indisponible.
7. Évaluer le système sur des incidents figés, sans utiliser la réponse du
   modèle pour décider du statut de qualité.

## Hors périmètre proposé

- remédiation autonome ;
- modification ou clôture d'incident par le modèle ;
- génération des règles de qualité ;
- chatbot généraliste ;
- entraînement ou fine-tuning d'un modèle ;
- envoi de données métier non nécessaires.

## Décisions avant le code

Le fournisseur, le modèle initial, la politique d'envoi, la persistance et le
budget ont été validés. Le cadrage fonctionnel est prêt pour l'implémentation.

## Avancement — lot 1 : frontière factuelle

Statut : implémenté et validé localement le 23 juillet 2026.

- contrat d'entrée `IncidentFactPackage` versionné en `1.0` ;
- contrat de sortie `GeneratedIncidentExplanation` strict et indépendant du
  fournisseur ;
- champs supplémentaires refusés à la validation ;
- liste blanche excluant notamment le texte d'erreur brut, le propriétaire, la
  localisation logique et le texte libre d'impact métier ;
- assainissement récursif des mesures, règles et références de preuve pour
  masquer secrets, DSN, jetons Bearer et adresses électroniques ;
- aucun appel réseau, SDK Gemini, secret ou changement de base de données dans
  ce lot.

### Preuves du lot 1

- 4 tests unitaires dédiés au contrat et à l'assainissement ;
- 36 tests sur 36 réussis dans un environnement Docker PostgreSQL isolé après
  application des migrations `0001` et `0002` ;
- analyse statique Ruff réussie ;
- environnement Docker temporaire supprimé après validation.

## Avancement — lot 2 : construction depuis le modèle commun

Statut : implémenté et validé localement le 23 juillet 2026.

- construction transactionnelle du paquet à partir d'un `incident_id` ;
- lecture de l'incident, du pipeline, du contrôle déclencheur et de l'actif
  associé depuis le seul schéma commun `observability` ;
- événements réduits à leur type et leur horodatage, sans acteur ni détails
  libres ;
- parcours récursif des actifs aval avec distance minimale et protection contre
  les cycles ;
- assainissement appliqué avant le retour du constructeur ;
- erreur explicite `FactPackageUnavailable` lorsque les faits minimaux sont
  absents ;
- aucune dépendance au connecteur Mobility, au dashboard ou au fournisseur IA.

### Preuves du lot 2

- test d'intégration d'un incident avec deux niveaux aval et un cycle de
  lineage ;
- vérification de l'absence du propriétaire, du texte libre d'impact métier, de
  la localisation contenant une DSN et des détails d'événement ;
- vérification de l'arrêt explicite pour un incident inexistant ;
- 38 tests sur 38 réussis après migrations `0001` et `0002` dans PostgreSQL
  isolé ;
- analyse statique Ruff réussie ;
- environnement Docker temporaire supprimé après validation.

## Avancement — lot 3 : fournisseur et mode dégradé

Statut : implémenté et validé localement le 23 juillet 2026.

- interface interne `IncidentExplanationProvider` indépendante de Gemini ;
- résultat horodaté distinguant explicitement le contenu IA du contenu
  déterministe ;
- mode dégradé factuel sans piste inventée lorsque le fournisseur est absent ou
  indisponible ;
- adaptateur `GeminiIncidentExplanationProvider` utilisant le SDK officiel
  `google-genai==2.13.0` ;
- modèle configurable avec `gemini-3.5-flash-lite` par défaut ;
- sortie Gemini contrainte par `GeneratedIncidentExplanation` et revalidée
  localement ;
- activation explicite par `GEMINI_ENABLED` et clé chargée comme secret depuis
  `GEMINI_API_KEY` ;
- Gemini désactivé lorsque l'activation ou la clé manque ;
- erreurs externes converties en code interne non sensible avant le fallback.

### Preuves du lot 3

- tests simulés de la sortie structurée et de la fermeture du client SDK ;
- vérification que la clé n'entre pas dans le contenu envoyé au modèle ;
- tests du fallback sans configuration et sur indisponibilité fournisseur ;
- aucun appel réseau vers Gemini pendant les tests ;
- 28 tests unitaires sur 28 réussis ;
- 42 tests sur 42 réussis après migrations `0001` et `0002` dans PostgreSQL
  isolé ;
- analyse statique Ruff réussie ;
- environnement Docker temporaire supprimé après validation.

## Avancement — lot 4 : persistance et audit

Statut : implémenté et validé localement le 23 juillet 2026.

- table `incident_explanations` liée à l'incident avec suppression restreinte ;
- une nouvelle ligne par génération, sans mise à jour d'une explication
  antérieure ;
- conservation du paquet factuel assaini et de la sortie structurée ;
- conservation du fournisseur, du modèle éventuel, de l'horodatage, des
  versions de contrats et du motif de mode dégradé ;
- contrainte imposant un modèle pour toute ligne marquée comme générée par IA ;
- service de persistance sans mutation de l'incident ni de son statut ;
- migration Alembic `0003` explicite et réversible.

### Preuves du lot 4

- deux générations du même incident créent deux identifiants d'audit distincts ;
- snapshot vérifié assaini avant stockage ;
- statut de l'incident vérifié inchangé après persistance ;
- 43 tests sur 43 réussis après migrations `0001`, `0002` et `0003` ;
- analyse statique Ruff réussie ;
- retour arrière `0003` vers `0002`, puis réapplication de `0003`, réussis ;
- environnement Docker temporaire supprimé après validation.

## Avancement — lot 5 : orchestration et intégration Streamlit

Statut : implémenté et validé localement le 23 juillet 2026.

- service d'orchestration lisant le paquet factuel, appelant le fournisseur hors
  transaction puis persistant le résultat dans une transaction distincte ;
- sélection de Gemini depuis la configuration, avec maintien automatique du
  mode dégradé déterministe lorsque Gemini est désactivé, non configuré ou
  indisponible ;
- variables Gemini transmises uniquement au service `dashboard` dans la
  composition Docker, sans valeur secrète inscrite dans le dépôt ;
- génération déclenchée manuellement depuis le détail d'un incident ;
- affichage distinct des faits, inconnues et pistes de diagnostic ;
- étiquetage explicite du fournisseur, du modèle éventuel, de l'horodatage et
  de la nature IA ou déterministe de chaque explication ;
- consultation de l'historique d'audit par ordre antéchronologique ;
- aucune mutation de l'incident, de son statut ou des contrôles de qualité.

### Preuves du lot 5

- test d'intégration couvrant lecture, génération déterministe et persistance
  dans des transactions séparées ;
- vérification qu'une ligne d'audit est créée et que le statut de l'incident
  reste inchangé ;
- requête du dashboard vérifiée sur un historique initialement vide ;
- migration `0003` appliquée avec succès sur PostgreSQL isolé ;
- 44 tests sur 44 réussis dans l'image Docker finale ;
- analyse statique Ruff réussie sans cache dans l'image non privilégiée ;
- aucun appel réseau vers Gemini et aucune clé réelle utilisés pendant la
  validation.

### Revue fonctionnelle interactive du lot 5

Revue effectuée localement le 23 juillet 2026 sur les deux pipelines présents
dans le modèle commun : `Trafic routier` et `Vélib`.

- migration du volume local existant de `0002` vers `0003` sans suppression de
  données ;
- navigation portefeuille, sélection de pipeline et consultation des incidents
  vérifiées dans Streamlit ;
- génération déterministe déclenchée manuellement pour un incident de chaque
  pipeline avec Gemini désactivé ;
- une ligne d'audit créée pour chaque incident et historique visible dans
  l'interface ;
- les deux incidents sont restés au statut `open` après génération ;
- fournisseur `deterministic`, modèle absent et inconnues déclarées affichés
  explicitement ;
- aucune erreur navigateur relevée et services PostgreSQL et Streamlit déclarés
  sains par Docker.

Le lot 5 est fonctionnellement accepté. Le Sprint 6 ne peut pas encore être
clos : le protocole d'évaluation versionné demandé par la feuille de route reste
à définir et à exécuter dans un lot 6.

## Avancement — lot 6 : protocole d'évaluation versionné

Statut : implémenté et validé localement le 23 juillet 2026.

- protocole `v1.0` formalisé dans
  `docs/evaluations/protocole-explications-incidents-v1.0.md` ;
- séparation explicite des pistes Gemini et fallback déterministe ;
- seuils bloquants et individuels validés avant implémentation ;
- moyenne arithmétique simple réservée à la piste Gemini ;
- moteur de décision sans analyse implicite du texte ni substitution à la revue
  humaine ;
- résultat local du fallback consigné sans le présenter comme une qualification
  de Gemini.

### Preuves du lot 6

- quatre tests unitaires couvrent l'acceptation Gemini, chaque échec bloquant,
  les seuils individuels, la moyenne globale et la piste déterministe ;
- 49 tests sur 49 réussis après migrations `0001`, `0002` et `0003` dans une
  base PostgreSQL Docker isolée ;
- analyse statique Ruff réussie ;
- 52 fichiers conformes au format canonique Ruff ;
- aucune donnée de la revue interactive locale utilisée ou modifiée par les
  tests isolés.

Le fallback déterministe et l'infrastructure d'évaluation ont d'abord été
qualifiés sans appel externe. La qualification Gemini a ensuite été exécutée
séparément selon le même protocole `v1.0`.

### Qualification Gemini réelle

Campagne exécutée le 23 juillet 2026 et documentée dans
`docs/evaluations/campagne-gemini-2026-07-23.md`.

- clé valide et modèle `gemini-3.5-flash-lite` accessible ;
- incompatibilité de l'ancien champ SDK `response_schema` identifiée sans
  exposer de donnée métier ni de secret ;
- passage à `response_json_schema` validé sans assouplir le contrat local ;
- première sortie réelle refusée avec un score global de 80, car aucune piste
  diagnostique n'était fournie ;
- frontière Gemini corrigée pour exiger entre une et trois vérifications
  prudentes, sans modifier le fallback déterministe ;
- seconde sortie réelle acceptée avec un score global de 96 ;
- audit Gemini conservé, aucun motif sensible détecté et incident resté au
  statut `open` ;
- validation finale : 49 tests réussis, analyse statique réussie et 52 fichiers
  conformes au format canonique.

Le Sprint 6 satisfait ses preuves de clôture. Sa clôture et son commit restent
soumis à la validation explicite de l'utilisateur.

Le budget est fixé à zéro pour le POC : tout dépassement de quota doit activer
le mode dégradé, jamais une facturation automatique.
