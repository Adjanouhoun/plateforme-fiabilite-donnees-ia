# Plateforme de Fiabilité et de Préparation des Données pour l'IA

Plateforme centralisée destinée à surveiller plusieurs pipelines de données,
contrôler leur fiabilité, historiser leurs incidents et évaluer leur aptitude à
alimenter des usages analytiques ou d'intelligence artificielle.

Le projet est actuellement dans sa phase de cadrage. Aucun composant de
production n'est encore déployé. Le socle local est développé par sprints
documentés.

## Principes directeurs

- cœur indépendant des pipelines supervisés ;
- intégration par connecteurs et contrats communs ;
- contrôles déterministes et auditables ;
- séparation entre faits mesurés et explications produites par l'IA ;
- développement et validation en local avant déploiement sur OVHcloud ;
- dimensionnement de la production fondé sur des mesures réelles.

## Documentation

- [Sprint 0 — État des lieux et cadrage](docs/sprints/sprint-00.md)
- [Sprint 1 — Socle local et modèle commun](docs/sprints/sprint-01.md)
- [Contrat fonctionnel minimal](docs/contracts/contrat-fonctionnel-minimal.md)
- [Feuille de route des sprints](docs/roadmap.md)
- [Modèle de données commun](docs/architecture/modele-commun.md)

## Prérequis locaux

- Git ;
- Docker Engine ou Docker Desktop ;
- Docker Compose v2.

Python n'est pas requis sur la machine hôte : le projet utilise Python 3.11
dans ses conteneurs.

## Démarrage local

Créer la configuration locale, puis remplacer le mot de passe d'exemple :

```bash
cp .env.example .env
```

Démarrer PostgreSQL :

```bash
docker compose up -d postgres_observability
```

Appliquer explicitement les migrations :

```bash
docker compose --profile tools run --rm migrate
```

Démarrer l'API :

```bash
docker compose up -d api
```

Vérifier les endpoints :

```text
http://127.0.0.1:8090/health/live
http://127.0.0.1:8090/health/ready
```

## Validation locale

```bash
docker compose --profile test build test
docker compose --profile test run --rm test ruff check .
docker compose --profile test run --rm test ruff format --check .
docker compose --profile test run --rm test pytest -q
docker compose --profile tools run --rm migrate alembic check
```

La migration n'est volontairement pas exécutée automatiquement au démarrage de
l'API. Une évolution du schéma reste ainsi une opération visible et contrôlée.
