# Contrat du lineage dbt Mobility

## Source autorisée

La source de vérité du lineage structurel Mobility est l'artefact dbt
`target/manifest.json`. Le fichier est fourni à la plateforme par un montage
Docker en lecture seule.

Variables de configuration :

- `MOBILITY_DBT_MANIFEST_HOST_PATH` : chemin du manifeste sur l'hôte ;
- `MOBILITY_DBT_PROJECT_NAME` : projet attendu, `dbt_mobility` par défaut ;
- `MOBILITY_DBT_MANIFEST_PATH` : chemin interne au conteneur, fixé à
  `/artifacts/mobility/manifest.json` dans Docker Compose.

## Validation

La collecte échoue visiblement lorsque :

- le fichier est absent, illisible ou n'est pas un objet JSON ;
- les métadonnées requises sont invalides ;
- le nom du projet diffère du projet configuré ;
- la clé d'un nœud diffère de son `unique_id` ;
- une source dbt attendue pour un pipeline est absente ;
- le pipeline ou son actif de monitoring n'existe pas dans le modèle commun.

## Mapping

- ressources `source` → actifs `dbt_source` ;
- ressources `model` → actifs `dbt_model` ;
- `unique_id` dbt → `external_asset_id` ;
- `relation_name` → `logical_location` ;
- `depends_on.nodes` → relation orientée source vers cible ;
- type de transformation → `dbt_dependency` ;
- origine de preuve → projet, source et cible du manifeste ;
- `metadata.generated_at` → date d'observation de la relation.

L'actif `model.dbt_mobility.fct_pipeline_runs` réutilise l'actif de monitoring
`pipeline-runs` déjà créé par le connecteur. Cette identité est fondée sur la
relation physique `schema_analytics.fct_pipeline_runs` et permet de conserver le
lien avec les contrôles et incidents existants.

## Appartenance aux pipelines

L'appartenance est calculée depuis les sources réellement utilisées par chaque
DAG et les descendants déclarés par dbt :

- Vélib : `raw_data.stg_raw_stations` et `monitoring_data.ingestion_runs` ;
- Trafic routier : `road_traffic_raw.road_traffic_observations` et
  `monitoring_data.traffic_ingestion_runs`.

Un actif partagé est dupliqué dans chaque pipeline concerné. Les relations ne
traversent pas artificiellement les copies.

## Idempotence et rétention

Un nouvel import met à jour la date d'observation d'une preuve identique. Il ne
supprime pas une relation absente du fichier courant, car cette absence pourrait
provenir d'un manifeste partiel. Une politique de péremption devra être décidée
avant le déploiement de production.

## Impact

L'exposition technique d'un incident est calculée depuis l'actif de son contrôle
déclencheur vers les actifs aval du lineage prouvé. Le parcours protège contre
les cycles et conserve la distance minimale.

Cette exposition ne modifie jamais `business_impact` ni `impact_origin`. En
l'absence d'une mesure ou déclaration autorisée, l'impact métier reste
`unknown`.

## Limites

- aucune preuve d'exécution d'une relation ;
- aucun lineage au niveau colonne ;
- aucune relation déduite du nom ou du SQL ;
- aucun indicateur métier fourni par le manifeste observé ;
- aucune suppression automatique des preuves anciennes.
