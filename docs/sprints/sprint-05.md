# Sprint 5 — Dépendances et impact

## Statut

Implémentation locale terminée et validation technique réalisée. Clôture
fonctionnelle en attente de validation explicite.

## Objectif issu de la feuille de route

Présenter les dépendances prouvées entre actifs et relier un incident aux actifs
et indicateurs susceptibles d'être affectés.

## État des lieux au 22 juillet 2026

### Plateforme de fiabilité

- le modèle commun contient déjà `data_assets` et `lineage_edges` ;
- une relation conserve sa source, sa cible, son type de transformation, son
  origine de preuve et sa date d'observation ;
- les auto-références sont interdites et une contrainte d'unicité protège les
  preuves identiques ;
- les incidents qualifient déjà leur impact comme `measured`, `declared` ou
  `unknown` ;
- l'interface du Sprint 4 sait afficher les actifs et les relations disponibles ;
- en l'absence de relation, elle affiche un état vide explicite et n'invente pas
  de graphe ;
- le connecteur Mobility ne crée actuellement aucune ligne dans
  `lineage_edges` ;
- les données locales contiennent un actif de monitoring par pipeline Mobility,
  mais aucun actif dbt détaillé.

### Preuve disponible dans Mobility

Le dépôt local `data-pipeline-mobility` contient un artefact dbt ignoré par Git :
`dbt_mobility/target/manifest.json`.

Mesures réalisées sur cet artefact :

- projet : `dbt_mobility` ;
- version dbt : `1.7.19` ;
- génération : `2026-07-19T00:00:09.734254Z` ;
- 13 modèles ;
- 4 sources ;
- 14 relations directes source-modèle ou modèle-modèle.

Les relations sont déclarées par dbt à partir des appels `source()` et `ref()`.
Le manifeste constitue donc une preuve de lineage **structurel**. Il ne prouve
pas qu'une relation a été parcourue par une exécution donnée.

Le contrat du Sprint 2 indique que la preuve de lineage d'exécution est
indisponible dans `schema_analytics.fct_pipeline_runs`. Cette limite reste
valide : le manifeste apporte une autre catégorie de preuve et ne doit pas être
présenté comme un lineage d'exécution.

### Limites observées

- `target/manifest.json` est un artefact généré et non versionné ;
- son emplacement n'est pas encore un contrat de configuration de la
  plateforme ;
- aucun manifeste n'est actuellement monté dans les conteneurs de la
  plateforme ;
- le manifeste sémantique observé ne fournit aucun indicateur métier exploitable ;
- aucune source ne fournit actuellement un impact métier chiffré ou déclaré ;
- le modèle ne contient pas de lineage au niveau colonne ;
- la date de génération du manifeste doit rester visible pour ne pas présenter
  une preuve ancienne comme actuelle.

## Décisions validées

- `manifest.json` est la source de vérité du lineage structurel Mobility ;
- les actifs dbt partagés sont dupliqués de manière contrôlée dans les pipelines
  concernés ;
- le lineage structurel ne doit jamais être présenté comme un lineage
  d'exécution ;
- l'exposition technique ne modifie pas l'impact métier.

## Périmètre réalisé

1. Lire un `manifest.json` dbt depuis un chemin explicitement configuré et monté
   en lecture seule.
2. Refuser visiblement un fichier absent, invalide ou appartenant à un projet
   inattendu.
3. Enregistrer les sources et modèles dbt comme actifs du modèle commun.
4. Enregistrer uniquement les relations directes déclarées dans
   `depends_on.nodes`, avec une origine de preuve traçable.
5. Rendre la collecte idempotente sans supprimer une relation dont l'absence
   pourrait seulement provenir d'un manifeste partiel.
6. Calculer l'exposition technique d'un incident à partir de son contrôle
   déclencheur et des actifs situés en aval dans le lineage prouvé.
7. Conserver l'impact métier à `unknown` tant qu'aucune mesure ou déclaration
   autorisée n'est disponible.
8. Afficher séparément dans Streamlit la preuve directe, l'exposition technique
   calculée et l'impact métier.

## Hors périmètre

- lineage d'exécution ;
- lineage au niveau colonne ;
- dépendances déduites du nom des tables ou de requêtes SQL analysées ;
- indicateurs métier inventés à partir des KPI techniques du tableau de bord ;
- impact financier ou utilisateur non fourni par une source autorisée ;
- assistance IA, réservée au Sprint 6.

## Implémentation

- commande dédiée `mobility_lineage_collector` ;
- manifeste monté en lecture seule et projet attendu configurable ;
- validation stricte des métadonnées et identifiants ;
- parcours des descendants depuis les sources propres à chaque DAG ;
- duplication contrôlée des actifs partagés ;
- import idempotent des actifs et relations ;
- origine et date de preuve conservées ;
- parcours récursif aval des incidents avec protection contre les cycles ;
- affichage séparé de l'exposition technique et de l'impact métier dans
  Streamlit ;
- contrat détaillé dans `docs/contracts/lineage-dbt-mobility.md`.

## Vérifications réalisées le 22 juillet 2026

- formatage Ruff : réussi sur 36 fichiers ;
- analyse statique Ruff : réussie ;
- migrations Alembic `0001` et `0002` appliquées sur une base isolée ;
- suite automatisée : 32 tests réussis ;
- manifeste réel Mobility accepté : projet `dbt_mobility`, dbt 1.7.19,
  génération du 19 juillet 2026 à 00:00:09 UTC ;
- deux imports successifs : même rapport de 18 actifs observés et 14 relations ;
- stockage réel : 9 actifs et 7 relations pour Vélib, 9 actifs et 7 relations
  pour Trafic routier ;
- scénario temporaire d'incident Vélib : 6 actifs exposés sur 4 niveaux, dont
  5 actifs aval ;
- contrôle navigateur réel : dépendances présentes, état vide absent et
  incident affiché avec impact métier `Inconnu` ;
- avertissement visible : l'exposition technique calculée ne constitue pas un
  impact métier mesuré ;
- mode opérateur resté en lecture seule pendant la validation.

## Preuves de clôture

- import reproductible et idempotent d'un manifeste dbt contrôlé ;
- origine et date de chaque relation visibles ;
- test d'un chemin source → modèle → modèle ;
- incident relié à son actif déclencheur et à ses actifs aval prouvés ;
- absence de manifeste ou de relation rendue explicitement ;
- impact technique calculé distingué de l'impact métier déclaré ou mesuré ;
- tests automatisés, validation Docker et contrôle réel dans le navigateur ;
- documentation du contrat d'intégration et des limites.

## Résultat

Les critères techniques du Sprint 5 sont satisfaits localement. Le lineage
d'exécution, le lineage colonne, les indicateurs métier et l'assistance IA
restent hors périmètre conformément aux décisions validées.
