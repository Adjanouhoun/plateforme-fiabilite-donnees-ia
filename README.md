# Plateforme de Fiabilité et de Préparation des Données pour l'IA

Plateforme centralisée destinée à surveiller plusieurs pipelines de données,
contrôler leur fiabilité, historiser leurs incidents et évaluer leur aptitude à
alimenter des usages analytiques ou d'intelligence artificielle.

Le projet est déployé en production sur OVHcloud et reste organisé en sprints
documentés. Il observe actuellement quatre pipelines issus de deux systèmes
sources, sans répliquer leurs données métier ni exposer leurs bases.

**Accès public :** [fiabilite.amadouadjanouhoun.fr](https://fiabilite.amadouadjanouhoun.fr)

## État validé en production

Au 28 juillet 2026, la plateforme regroupe :

- 4 pipelines actifs : Vélib, trafic routier, France Travail et La Bonne
  Alternance ;
- 500 exécutions historisées ;
- 20 actifs de données et 14 relations de lineage dbt ;
- 50 tests dbt ciblés réussis lors de la remédiation Mobility ;
- une exposition HTTPS via Nginx, les services applicatifs et PostgreSQL restant
  accessibles uniquement sur le réseau interne du VPS.

Les collecteurs emploient des comptes PostgreSQL dédiés, limités à la lecture
des seules tables contractuelles : `schema_analytics.fct_pipeline_runs` pour
Mobility et `app.sync_runs` pour l'assistant emploi.

## Principes directeurs

- cœur indépendant des pipelines supervisés ;
- intégration par connecteurs et contrats communs ;
- contrôles déterministes et auditables ;
- séparation entre faits mesurés et explications produites par l'IA ;
- développement et validation en local avant déploiement sur OVHcloud ;
- dimensionnement de la production fondé sur des mesures réelles.

## Architecture supervisée

Deux connecteurs indépendants normalisent les métadonnées vers le même modèle
PostgreSQL `observability` :

| Système source | Pipelines observés | Données lues |
| --- | --- | --- |
| Plateforme Mobilité | Vélib, trafic routier | exécutions dbt consolidées uniquement |
| Assistant candidature emploi | France Travail, La Bonne Alternance | métadonnées de synchronisation uniquement |

Les règles de qualité et la gestion d'incidents sont déterministes. Gemini est
optionnel et encadré : il peut expliquer des faits déjà mesurés, mais ne décide
ni de l'état de santé d'un pipeline ni d'une action opérationnelle.

## Documentation

- [Sprint 0 — État des lieux et cadrage](docs/sprints/sprint-00.md)
- [Sprint 1 — Socle local et modèle commun](docs/sprints/sprint-01.md)
- [Sprint 2 — Connecteur Mobility](docs/sprints/sprint-02.md)
- [Sprint 3 — Contrôles et incidents déterministes](docs/sprints/sprint-03.md)
- [Sprint 4 — Interface Streamlit multi-pipelines](docs/sprints/sprint-04.md)
- [Sprint 5 — Dépendances et impact](docs/sprints/sprint-05.md)
- [Sprint 6 — Assistance IA contrôlée](docs/sprints/sprint-06.md)
- [Sprint 7 — Second connecteur et portabilité](docs/sprints/sprint-07.md)
- [Sprint 8 — Qualification et déploiement OVHcloud](docs/sprints/sprint-08.md)
- [Contrat fonctionnel minimal](docs/contracts/contrat-fonctionnel-minimal.md)
- [Mapping du connecteur Mobility](docs/contracts/mapping-mobility.md)
- [Mapping du connecteur emploi](docs/contracts/mapping-assistant-candidature-emploi.md)
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

Importer le lineage structurel dbt Mobility après la collecte des exécutions :

```bash
docker compose --profile tools run --rm mobility_lineage_collector
```

Le manifeste est monté en lecture seule. Son chemin hôte est configuré par
`MOBILITY_DBT_MANIFEST_HOST_PATH`. Cet import ne constitue pas une preuve de
lineage d'exécution.

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

## Collecte locale de l'assistant candidature emploi

Le connecteur lit uniquement les métadonnées de `app.sync_runs`. Les CV, les candidatures et le contenu des offres sont hors périmètre. Après avoir renseigné une URL de lecture seule dans `EMPLOYMENT_DATABASE_URL`, exécuter :

```bash
docker compose --profile tools run --rm employment_collector
```

Le mapping, les champs indisponibles et les contrôles sont documentés dans [le contrat emploi](docs/contracts/mapping-assistant-candidature-emploi.md).

Pour relancer la collecte locale sans inscrire le mot de passe lecteur dans un
fichier, utiliser le lanceur qui récupère le secret dans le trousseau macOS :

```bash
./scripts/run_employment_collector_local.sh
```

Le conteneur PostgreSQL de l'application emploi doit être démarré. Le script
relie uniquement son réseau Docker interne au réseau de la plateforme ; aucun
port de base de données n'est publié sur le Mac.

## Déploiement OVHcloud

Le déploiement de production est décrit dans `deploy/ovh/`. Il démarre seulement
PostgreSQL, l'API FastAPI et le dashboard Streamlit ; les collecteurs sont des
commandes visibles et ponctuelles. Les variables sensibles résident dans le
fichier `.env` privé du VPS et ne doivent jamais être ajoutées au dépôt.

Après une mise à jour validée, appliquer les migrations puis démarrer les
services avec le profil de production :

```bash
docker compose -f docker-compose.yml -f deploy/ovh/docker-compose.prod.yml \
  run --rm migrate
docker compose -f docker-compose.yml -f deploy/ovh/docker-compose.prod.yml \
  up -d postgres_observability api dashboard
```

Les collecteurs de production rejoignent uniquement les réseaux Docker internes
de leurs sources. Avant une collecte Mobility, vérifier que la vue dbt
`schema_analytics.fct_pipeline_runs` est bien matérialisée ; cette vérification
est documentée dans le [Sprint 8](docs/sprints/sprint-08.md).
