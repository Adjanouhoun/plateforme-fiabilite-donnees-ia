# Mapping du connecteur Mobility

## Statut

Validé le 22 juillet 2026 pour implémentation.

## Source

```text
schema_analytics.fct_pipeline_runs
```

Cette vue dbt normalise déjà les exécutions Vélib et trafic. Le connecteur ne
lira que les colonnes documentées dans le présent contrat.

## Identification des pipelines

| `dag_id` source | Clé cible proposée | Nom d'affichage |
|---|---|---|
| `ingest_and_transform_velib` | `mobility.velib` | Vélib |
| `ingest_paris_road_traffic` | `mobility.road_traffic` | Trafic routier |

Toute ligne portant un autre `dag_id` sera rejetée comme non mappée. Elle ne
sera pas rattachée automatiquement à un pipeline existant.

## Mapping des pipelines

| Champ cible | Source | Règle |
|---|---|---|
| `pipeline_key` | configuration | clé stable indiquée ci-dessus |
| `display_name` | configuration validée | nom indiqué ci-dessus |
| `description` | configuration | obligatoire pour l'enregistrement initial |
| `owner` | configuration | obligatoire, absent de la source |
| `environment` | configuration | obligatoire : `local` ou `production` |
| `expected_frequency_minutes` | DAG et documentation | `60` pour les deux pipelines |
| `criticality` | configuration | obligatoire, absente de la source |
| `is_active` | configuration | obligatoire |

## Mapping des exécutions

| Champ cible `pipeline_runs` | Colonne source | Transformation |
|---|---|---|
| `pipeline_id` | `dag_id` | résolution via la table de mapping validée |
| `external_run_id` | `pipeline_run_id` | copie exacte |
| `started_at` | `started_at` | copie avec fuseau horaire |
| `ended_at` | `finished_at` | copie avec fuseau horaire |
| `status` | `status` | `success` → `succeeded`, `failed` → `failed` |
| `rows_read` | `records_received` | copie exacte |
| `rows_written` | `changed_record_count` | insertions + mises à jour |
| `rows_rejected` | aucune | `NULL`, non mesuré par Mobility |
| `rows_unchanged` | `records_unchanged` | copie exacte |
| `error_message` | `error_message` | assainissement avant stockage |
| `ingested_at` | aucune | horodatage d'insertion de la plateforme |

Tout statut différent de `success` ou `failed` sera conservé sous la forme
normalisée `unknown` et signalé dans le rapport de collecte. Il ne sera pas
converti en succès par défaut.

## Assainissement des erreurs proposé

Avant stockage, le connecteur devra :

1. supprimer les paramètres sensibles présents dans les URL ;
2. masquer les valeurs correspondant à des mots de passe, jetons ou clés ;
3. supprimer les chaînes de connexion contenant des identifiants ;
4. limiter la taille du message conservé ;
5. ne jamais écrire le message brut dans les journaux.

La longueur maximale validée est de 2 000 caractères. Les motifs de masquage
seront couverts par des tests automatisés.

## Champs explicitement indisponibles

- nombre de lignes rejetées ;
- résultats détaillés des tests dbt ;
- propriétaire métier ;
- criticité métier ;
- environnement de déploiement ;
- preuve de lineage d'exécution ;
- impact métier d'une exécution échouée.

Un champ indisponible ne doit jamais être remplacé par zéro, `false` ou une
valeur positive supposée, sauf lorsqu'une règle métier documentée prouve cette
valeur.

## Règles de lecture

- transaction PostgreSQL déclarée en lecture seule ;
- aucune instruction DDL ou DML envoyée à Mobility ;
- sélection limitée aux colonnes du contrat ;
- filtre limité aux `dag_id` autorisés ;
- ordre stable par `started_at`, puis `pipeline_run_id` ;
- relecture complète de l'historique au Sprint 2, l'unicité cible absorbant les
  répétitions ;
- délai d'attente et erreurs de connexion rendus visibles sans exposer le DSN.

## Rapprochement attendu sur l'échantillon local

| Pipeline | Lignes source | Lignes cibles attendues au premier import |
|---|---:|---:|
| `mobility.velib` | 13 | 13 |
| `mobility.road_traffic` | 5 | 5 |
| Total | 18 | 18 |

Une deuxième collecte du même historique doit conserver exactement 18 lignes
cibles.
