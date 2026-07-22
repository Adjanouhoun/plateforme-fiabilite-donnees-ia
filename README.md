# Plateforme de Fiabilité et de Préparation des Données pour l'IA

Plateforme centralisée destinée à surveiller plusieurs pipelines de données,
contrôler leur fiabilité, historiser leurs incidents et évaluer leur aptitude à
alimenter des usages analytiques ou d'intelligence artificielle.

Le projet dispose désormais d'un socle local fonctionnel et d'un premier
connecteur validé sur les métadonnées réelles du pipeline Mobility. Aucun
composant de production n'est encore déployé. Le développement reste organisé
en sprints documentés.

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
- [Sprint 2 — Connecteur Mobility](docs/sprints/sprint-02.md)
- [Sprint 3 — Contrôles et incidents déterministes](docs/sprints/sprint-03.md)
- [Sprint 4 — Interface Streamlit multi-pipelines](docs/sprints/sprint-04.md)
- [Contrat fonctionnel minimal](docs/contracts/contrat-fonctionnel-minimal.md)
- [Mapping du connecteur Mobility](docs/contracts/mapping-mobility.md)
- [Règles de qualité et incidents](docs/contracts/regles-qualite-incidents.md)
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

Démarrer le tableau de bord :

```bash
docker compose up -d dashboard
```

L'interface est disponible sur `http://127.0.0.1:8501`. Par défaut,
`OPERATOR_NAME` est vide et les incidents sont consultables en lecture seule.
Renseigner explicitement cette variable dans `.env` pour autoriser les actions
d'acquittement et de clôture en environnement local.

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

## Collecte locale de Mobility

Le connecteur lit uniquement
`schema_analytics.fct_pipeline_runs`, dans une transaction PostgreSQL forcée en
lecture seule. Renseigner dans `.env` une URL vers la base Mobility accessible
depuis Docker, puis exécuter :

```bash
docker compose --profile tools run --rm mobility_collector
```

Le rapport JSON indique le nombre de lignes lues, insérées ou déjà présentes,
les contrôles créés, les échecs, les absences de mesure, les incidents actifs
ainsi que tout DAG ou statut non reconnu. Il n'affiche ni le DSN ni les messages
d'erreur sources. Le mapping exact et les limites du connecteur sont décrits
dans [le contrat Mobility](docs/contracts/mapping-mobility.md).
