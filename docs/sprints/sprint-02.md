# Sprint 2 — Connecteur Mobility en lecture seule

## Statut

Clôturé et accepté par le porteur du projet le 22 juillet 2026.

## Objectif

Collecter les métadonnées d'exécution réellement exposées par
`data-pipeline-mobility`, les convertir vers le modèle commun et les enregistrer
de manière idempotente, sans modifier les DAG ni les données métier de Mobility.

## Sources examinées

- dépôt local `data-pipeline-mobility` ;
- branche `ops/ovh-production-deployment` ;
- schémas SQL de monitoring versionnés ;
- modèles dbt de monitoring ;
- volume PostgreSQL local existant ;
- sauvegardes locales marquées comme vérifiées ;
- schéma et agrégats de la base locale réelle.

## Méthode d'inspection

Seul le conteneur `postgres_destination` a été démarré. Airflow, Superset,
pgAdmin et les bases de métadonnées sont restés arrêtés.

Les requêtes ont porté sur :

- `information_schema` ;
- les comptes et statuts agrégés ;
- les valeurs nulles ;
- l'unicité des identifiants ;
- les formats d'identifiants externes ;
- la liste des rôles PostgreSQL.

Les messages d'erreur et les données métier détaillées n'ont pas été affichés.
Le conteneur PostgreSQL a été arrêté après l'inspection et son volume a été
conservé.

## Résultats vérifiés

### Pipelines exposés

| Pipeline | DAG | Tâche observée | Planification documentée |
|---|---|---|---|
| Vélib | `ingest_and_transform_velib` | `extract_and_load_velib_task` | horaire |
| Trafic routier | `ingest_paris_road_traffic` | `extract_and_load_road_traffic` | horaire, minute 35 |

### Historique local

| Source | Exécutions | Première | Dernière | Succès | Échecs |
|---|---:|---|---|---:|---:|
| Vélib | 13 | 2026-07-17 23:47 UTC | 2026-07-19 00:00 UTC | 13 | 0 |
| Trafic routier | 5 | 2026-07-18 02:24 UTC | 2026-07-18 15:38 UTC | 5 | 0 |

Les 18 identifiants `pipeline_run_id` de la vue unifiée sont non nuls et
distincts. Les dates de début et de fin ainsi que les volumes nécessaires au
mapping sont présents sur les 18 lignes.

Aucun message d'erreur n'est renseigné dans cet échantillon, car aucune
exécution observée n'a échoué. Le comportement de nettoyage d'un message
d'erreur devra donc être testé avec des données contrôlées, pas affirmé à partir
de cet historique.

### Résultats dbt

Les DAG exécutent des contrôles dbt, mais aucune table persistante portant un
nom de test, d'audit ou de résultat n'a été trouvée dans la base. Le connecteur
du Sprint 2 ne collectera donc pas de résultats dbt détaillés.

### Sécurité de la source locale

La base locale expose un seul rôle applicatif : `data_engineer`. Ce rôle peut se
connecter et possède les droits superutilisateur.

Une transaction déclarée en lecture seule protégera les opérations normales du
connecteur, mais ne remplace pas un rôle PostgreSQL dédié. La création d'un tel
rôle modifierait les permissions de Mobility et requiert une décision séparée.

## Décisions techniques proposées

1. La source primaire du connecteur sera
   `schema_analytics.fct_pipeline_runs`.
2. Les pipelines seront identifiés par leur `dag_id`, plus stable que leur nom
   d'affichage accentué.
3. Les identifiants externes déjà préfixés de la vue seront conservés.
4. La collecte utilisera une transaction explicitement en lecture seule.
5. Aucun message d'erreur brut ne sera journalisé.
6. Les champs absents resteront nuls ou seront fournis par une configuration
   obligatoire ; ils ne seront jamais inventés.
7. Le Sprint 2 relira l'historique disponible à chaque collecte. Le faible
   volume observé rend cette stratégie vérifiable et l'unicité cible absorbera
   les répétitions. Un curseur incrémental ne sera ajouté qu'après mesure d'un
   besoin réel.
8. L'idempotence sera assurée par la contrainte existante
   `(pipeline_id, external_run_id)`.

## Informations à valider avant implémentation

- propriétaire déclaré de chacun des deux pipelines ;
- criticité métier de chacun des deux pipelines ;
- autorisation ou report de la création d'un compte PostgreSQL dédié en lecture
  seule ;
- règle de conservation des messages d'erreur assainis.

L'environnement ne sera pas déduit de la source : il sera fourni explicitement
par la configuration du connecteur (`local`, puis `production`).

## Arbitrages validés

- propriétaire déclaré : `data-engineering` pour les deux pipelines ;
- criticité : `medium` pour les deux pipelines en l'absence de SLA critique ;
- sécurité locale : transaction forcée en lecture seule ;
- rôle PostgreSQL dédié : reporté à la qualification de production OVHcloud ;
- messages d'erreur : secrets masqués et longueur limitée à 2 000 caractères.

## Hors périmètre

- modification des DAG Mobility ;
- collecte des données Vélib ou trafic elles-mêmes ;
- extraction de résultats dbt non persistés ;
- ouverture automatique d'incidents ;
- déploiement sur OVHcloud ;
- synchronisation temps réel.

## Critères de clôture proposés

- mapping source-cible validé ;
- connexion exécutée dans une transaction en lecture seule ;
- import exact des 18 exécutions locales ;
- seconde collecte sans doublon ;
- statuts et volumes rapprochés avec la source ;
- champs indisponibles enregistrés comme tels ;
- erreurs de connexion et schémas incompatibles rendus visibles ;
- secrets absents des journaux et du dépôt ;
- tests unitaires et d'intégration verts ;
- documentation d'exploitation locale mise à jour.

## Implémentation réalisée

- connecteur PostgreSQL isolé dans `pfpd_ia.connectors.mobility` ;
- mapping explicite des deux DAG vers les clés communes ;
- transaction source forcée en lecture seule et vérifiée avant lecture ;
- insertion idempotente par `(pipeline_id, external_run_id)` ;
- conservation de `rows_rejected` à `NULL` ;
- statuts non reconnus normalisés en `unknown` et listés dans le rapport ;
- DAG non mappés exclus de l'import et listés dans le rapport ;
- messages d'erreur assainis avant stockage et jamais écrits bruts dans la
  sortie du collecteur ;
- échec du collecteur rendu visible sans afficher la chaîne de connexion ni le
  détail potentiellement sensible de l'exception ;
- service Docker dédié, lancé uniquement avec le profil `tools`.

## Résultats de validation

### Validation automatisée

- pytest : 14 tests réussis, zéro échec ;
- Ruff : aucun défaut ;
- Ruff format : 20 fichiers correctement formatés ;
- test d'intégration : lecture seule, assainissement et idempotence vérifiés sur
  des données contrôlées.

### Rapprochement avec l'historique local réel

Premier passage :

| Indicateur | Résultat |
|---|---:|
| Lignes source | 18 |
| Lignes insérées | 18 |
| Doublons | 0 |
| DAG inconnus | 0 |
| Statuts inconnus | 0 |
| Transaction source en lecture seule | oui |

Deuxième passage sur le même historique : 18 lignes relues, zéro insertion et
18 doublons absorbés. La cible conserve exactement 18 exécutions distinctes.

Le rapprochement agrégé est exact :

| Pipeline | Exécutions | Lignes lues | Lignes écrites | Lignes inchangées |
|---|---:|---:|---:|---:|
| `mobility.velib` | 13 | 19 708 | 9 082 | 10 626 |
| `mobility.road_traffic` | 5 | 41 706 | 8 937 | 32 769 |

Les 18 valeurs cibles de `rows_rejected` sont `NULL`, conformément au contrat.
Aucun message d'erreur réel n'était disponible dans l'échantillon ; son
assainissement est donc démontré uniquement par les tests contrôlés.

## Limites maintenues

- le compte local Mobility reste superutilisateur ; la transaction en lecture
  seule réduit le risque opérationnel mais ne remplace pas un rôle dédié ;
- la création du rôle à privilèges minimaux reste obligatoire avant la
  qualification OVHcloud ;
- la collecte relit tout l'historique, acceptable pour les 18 lignes mesurées ;
- les résultats détaillés des tests dbt ne sont pas collectables tant qu'ils ne
  sont pas persistés par Mobility.
