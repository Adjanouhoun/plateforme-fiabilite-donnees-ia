# Sprint 1 — Socle local et modèle commun

## Statut

Clôturé le 22 juillet 2026.

Le socle local, le modèle commun, les migrations, les tests et les résultats de
validation ont été acceptés par le porteur du projet.

## Objectif

Créer un socle local reproductible et le modèle de stockage commun sans intégrer
encore un pipeline réel.

## État des lieux initial

- poste local macOS ARM64 ;
- Python système 3.9.6, non retenu pour le projet ;
- Docker 29.5.3 et Docker Compose 5.1.4 disponibles ;
- Mobility et sa CI utilisent Python 3.11 ;
- aucun code applicatif présent au début du sprint.

## Décisions validées

- Python 3.11 exécuté dans des conteneurs ;
- PostgreSQL 15 comme stockage central ;
- SQLAlchemy 2 pour le modèle relationnel ;
- Alembic pour les migrations explicites ;
- Pydantic pour la configuration ;
- FastAPI comme frontière applicative ;
- pytest et Ruff pour la validation ;
- structure Python `src/` ;
- image d'exécution séparée de l'image de test.

## Périmètre

Le sprint couvre :

- configuration locale sans secret versionné ;
- conteneurs PostgreSQL et API ;
- migration initiale réversible ;
- tables communes et contraintes d'intégrité ;
- endpoints de vie et de disponibilité ;
- tests unitaires et d'intégration ;
- intégration continue.

Le sprint ne couvre pas :

- connecteur Mobility ;
- interface Streamlit ;
- règles de détection d'incidents ;
- intelligence artificielle ;
- déploiement OVHcloud.

## Modèle commun initial

Les six objets fonctionnels sont stockés dans le schéma `observability` :

- pipelines ;
- exécutions ;
- actifs de données ;
- contrôles de qualité ;
- incidents ;
- relations de lineage.

Une table technique supplémentaire, `incident_events`, conserve l'historique
des changements d'un incident exigé par le contrat fonctionnel.

## Points à vérifier avant clôture

- construction de l'image sur ARM64 ;
- application et retour arrière de la migration ;
- correspondance entre le modèle SQLAlchemy et la migration ;
- contraintes d'idempotence ;
- démarrage de l'API après migration ;
- endpoints de santé ;
- suite de tests et formatage ;
- absence de secret et état Git propre après publication.

## Résultats obtenus

- image Python 3.11 construite localement sur ARM64 ;
- API exécutée sous l'utilisateur non-root `app` ;
- PostgreSQL et API déclarés sains par Docker ;
- migration `0001` appliquée avec succès ;
- retour arrière jusqu'à `base` appliqué avec suppression vérifiée du schéma ;
- migration réappliquée avec succès ;
- comparaison Alembic : aucune opération manquante ;
- endpoint `/health/live` validé ;
- endpoint `/health/ready` validé avec présence du schéma ;
- Ruff : aucun défaut et douze fichiers Python correctement formatés ;
- pytest : dix tests réussis, zéro échec.

Les tests couvrent notamment :

- configuration obligatoire de la base ;
- enregistrement des tables du modèle commun ;
- présence des contraintes d'idempotence ;
- création réelle des tables par migration ;
- disponibilité de la base et du schéma ;
- unicité de `pipeline_key` ;
- refus d'un volume d'exécution négatif ;
- endpoint de vie indépendant de PostgreSQL.

## Incidents rencontrés et arbitrages

### Contexte Docker des tests

Le dossier `tests` était initialement exclu du contexte Docker. L'exclusion a
été retirée pour l'image de test, sans ajouter les tests à l'image d'exécution.

### Caches sous utilisateur non-root

Ruff et pytest ne pouvaient pas écrire dans `/app`. Les caches ont été déplacés
vers `/tmp` ; les permissions de l'application n'ont pas été élargies.

### Schéma Alembic

L'utilisateur PostgreSQL porte le même nom que le schéma `observability`.
PostgreSQL le rendait donc implicitement prioritaire via `"$user"` dans le
`search_path`, ce qui faussait la réflexion des clés étrangères.

Alembic force désormais `public` comme schéma implicite pendant ses opérations.
Sa table de version reste dans `public`, tandis que les tables applicatives sont
isolées dans `observability`.

## Critères de clôture

Les résultats ci-dessus ont été acceptés. Le connecteur Mobility reste
explicitement réservé au Sprint 2.
