# Mapping — assistant candidature emploi

## Périmètre et lecture seule

Ce connecteur lit exclusivement `app.sync_runs` dans la base de l'assistant candidature emploi. Il ne lit ni offres détaillées, ni CV, ni profils candidats, ni brouillons ou événements de candidature.

La transaction de la source est explicitement déclarée en lecture seule avant toute requête. Le compte de base de données devra être limité à `SELECT` sur `app.sync_runs` lors du raccordement effectif.

## Pipelines observés

| Pipeline commun | Filtre source | Cadence déclarée | Actif observé |
| --- | --- | ---: | --- |
| `emploi.france_travail` | `provider = france_travail` | 360 min | métadonnées des synchronisations France Travail |
| `emploi.la_bonne_alternance` | `provider = la_bonne_alternance` | 1 440 min | métadonnées des synchronisations La Bonne Alternance |

## Champs conservés

| Source `app.sync_runs` | Modèle commun | Traitement |
| --- | --- | --- |
| `id` | `pipeline_runs.external_run_id` | identifiant externe idempotent |
| `provider` | rattachement à un pipeline | filtre contractuel |
| `status` | `pipeline_runs.status` | `success`, `failed`, `running`; autre valeur = `unknown` |
| `started_at`, `completed_at` | début et fin | fin absente admise pour une exécution en cours |
| `offers_seen` | `rows_read` | compteur observé, pas un nombre d'offres exportées |
| `segments_expected`, `segments_completed` | contrôle `completeness` | égalité stricte des compteurs |
| `error_summary` | `error_message` | assaini avant stockage |

`rows_written`, `rows_rejected` et `rows_unchanged` restent vides : la source ne fournit pas de métrique permettant de les établir sans les inventer.

## Contrôles

- schéma et unicité par fournisseur ;
- fraîcheur : avertissement à deux cadences, erreur à trois cadences ;
- complétude des segments pour chaque exécution ;
- cohérence de volume seulement après cinq exécutions réussies comparables.

Un échec remonté par la source est conservé comme tel.
