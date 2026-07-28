# Sprint 7 — Second connecteur et portabilité

## État des lieux

Le cœur stocke des pipelines, exécutions, actifs et contrôles sans dépendance métier Mobility. L'assistant candidature emploi fournit une structure différente : des synchronisations par fournisseur dans `app.sync_runs`.

## Décision de mapping

Deux pipelines sont observés, France Travail et La Bonne Alternance. Seules les métadonnées de synchronisation sont admises. Les données de candidats et les contenus des offres restent hors périmètre.

## Réalisation

- adaptateur `connectors.employment` indépendant de l'interface ;
- transaction source verrouillée en lecture seule ;
- import idempotent et assainissement des erreurs ;
- contrôles de schéma, unicité, fraîcheur, complétude et volume ;
- service Docker manuel `employment_collector` dans le profil `tools`.

## Écart de contrat assumé

La source ne fournit pas les compteurs nécessaires à la règle générique `rows_read = rows_written + rows_unchanged`. Le connecteur enregistre donc seulement `offers_seen` comme compteur lu et laisse les autres compteurs non mesurés.

## Preuve de portabilité attendue

Les deux pipelines emploi doivent apparaître sans modification de l'interface Streamlit, via les requêtes génériques du modèle commun. Le raccordement à la base de production reste conditionné à la création d'un rôle PostgreSQL dédié, limité à `SELECT` sur `app.sync_runs`.
