# Sprint 3 — Contrôles et incidents déterministes

## Statut

Clôturé et accepté par le porteur du projet le 22 juillet 2026.

## Objectif

Évaluer des règles de qualité explicites sur les métadonnées Mobility,
historiser leurs preuves et gérer un cycle de vie minimal d'incident sans
déléguer la décision à un modèle d'intelligence artificielle.

## État des lieux

- le Sprint 2 a importé 18 exécutions réelles et prouvé l'idempotence du
  connecteur ;
- le schéma commun contient déjà `data_assets`, `quality_checks`, `incidents`
  et `incident_events` ;
- aucune politique automatique d'ouverture ou de résolution d'incident
  n'existe encore ;
- Mobility déclare une fraîcheur dbt avec avertissement après 2 heures et erreur
  après 6 heures ;
- Mobility ne persiste pas les résultats détaillés de ses tests dbt ;
- aucun seuil officiel d'anomalie de volume n'est déclaré dans Mobility.

## Mesures vérifiées

| Pipeline | Exécutions | Minimum reçu | Médiane | Maximum reçu | Incohérences | Volumes nuls |
|---|---:|---:|---:|---:|---:|---:|
| Vélib | 13 | 1 516 | 1 516 | 1 516 | 0 | 0 |
| Trafic routier | 5 | 5 958 | 8 937 | 8 937 | 0 | 0 |

Une incohérence désigne ici une exécution où le volume lu diffère de la somme
des lignes écrites et inchangées.

## Règles validées

### Fraîcheur

- conforme jusqu'à 2 heures depuis la dernière exécution réussie ;
- échec de sévérité `warning` au-delà de 2 heures ;
- échec de sévérité `error` au-delà de 6 heures ;
- absence d'exécution réussie : `not_measured`.

### Volume

- comparaison du volume courant avec la médiane des cinq exécutions réussies de
  référence ;
- anomalie si l'écart absolu dépasse 50 % ;
- moins de cinq références disponibles : `not_measured`.

La fenêtre de référence exclura l'exécution courante afin que la valeur évaluée
ne modifie pas son propre seuil.

### Unicité

Le nombre d'identifiants externes dupliqués dans la source doit être nul. Le
contrôle cible complète, sans la remplacer, la contrainte d'unicité SQL qui
protège l'import.

### Schéma et cohérence

- la vue source doit exposer les colonnes et types compatibles définis par le
  contrat du Sprint 2 ;
- pour chaque exécution mesurable, le volume lu doit être égal à la somme du
  volume écrit et du volume inchangé ;
- un champ requis absent produit un échec de schéma visible, pas un succès.

## Actifs techniques

Un actif technique sera enregistré pour chacun des deux pipelines. Les deux
actifs référenceront la vue partagée `schema_analytics.fct_pipeline_runs`, avec
leur filtre `dag_id` explicite.

- propriétaire : `data-engineering` ;
- sensibilité : `internal` ;
- contenu supervisé : métadonnées d'exécution uniquement.

## Cycle de vie validé

1. un contrôle en échec ouvre un incident s'il n'en existe pas déjà un pour la
   même règle et le même actif ;
2. un nouvel échec met à jour la preuve sans créer de doublon ;
3. un opérateur peut acquitter l'incident ;
4. un retour à la conformité résout automatiquement l'incident ;
5. la clôture reste une action explicite de l'opérateur ;
6. chaque transition est ajoutée à `incident_events`.

L'ouverture commence dès la sévérité `warning`.

## Périmètre

- moteur de règles déterministe ;
- stockage idempotent des contrôles ;
- prévention des incidents ouverts en doublon ;
- transitions `open`, `acknowledged`, `resolved` et `closed` ;
- scénarios contrôlés de retard, doublon, rupture de schéma, anomalie de volume
  et incohérence ;
- raccordement aux métadonnées Mobility en lecture seule.

## Hors périmètre

- interface Streamlit, réservée au Sprint 4 ;
- collecte des données métier Vélib ou trafic ;
- persistance des résultats dbt dans Mobility ;
- explication par IA ;
- déploiement OVHcloud ;
- blocage d'une publication, qui nécessite un point de publication explicite.

## Critères de clôture

- chaque règle possède une preuve structurée et un test reproductible ;
- `not_measured` est distingué de `passed` ;
- une répétition ne crée ni contrôle ni incident en doublon ;
- les transitions d'incident sont historisées ;
- le retour à la normale résout automatiquement l'incident ;
- aucune donnée métier ni aucun secret n'est stocké dans les preuves ;
- les résultats réels Mobility sont rapprochés et documentés ;
- tests, formatage et contrôle Alembic réussis.

## Implémentation réalisée

- moteur de règles indépendant du connecteur ;
- création idempotente des contrôles et preuves structurées ;
- actifs techniques Mobility enregistrés avec sensibilité `internal` ;
- inspection du schéma source avant la requête de collecte ;
- contrôles de fraîcheur, volume, unicité et cohérence raccordés à Mobility ;
- index unique partiel empêchant deux incidents actifs pour la même règle et le
  même actif ;
- ouverture, acquittement, résolution automatique et clôture historisés ;
- migration Alembic `0002` réversible ;
- rapport du collecteur étendu aux contrôles et incidents ;
- tests Mobility isolés par des clés uniques afin de préserver les données
  locales réelles.

## Scénarios automatisés

Les tests reproduisent et vérifient :

- fraîcheur conforme, en avertissement, en erreur et non mesurable ;
- anomalie de volume à la frontière validée de 50 % ;
- historique insuffisant donnant `not_measured` ;
- identifiant dupliqué ;
- volume incohérent ;
- colonne absente ou type incompatible ;
- rupture de schéma empêchant la requête incompatible ;
- répétition idempotente d'un contrôle ;
- incident ouvert, acquitté, alimenté par un nouvel échec, résolu puis clos ;
- conservation des données Mobility réelles pendant les tests.

## Résultats de validation

### Validation automatisée

- pytest : 24 tests réussis, zéro échec ;
- Ruff : aucun défaut ;
- migration temporaire : `0001 → 0002 → 0001 → 0002` réussie ;
- colonne et index de déduplication présents après réapplication ;
- base temporaire supprimée après validation.

### Exécution sur les métadonnées réelles

Premier passage :

| Indicateur | Résultat |
|---|---:|
| Lignes source | 18 |
| Exécutions insérées | 18 |
| Contrôles insérés | 42 |
| Contrôles en échec | 2 |
| Contrôles non mesurés | 10 |
| Incidents actifs | 2 |
| DAG ou statuts inconnus | 0 |

Deuxième passage dans le même créneau : 18 exécutions reconnues comme doublons,
zéro exécution insérée, zéro contrôle inséré et toujours exactement deux
incidents actifs.

### Répartition réelle

| Pipeline | Contrôle | Résultat |
|---|---|---|
| Vélib | schéma | 1 `passed` |
| Vélib | unicité | 1 `passed` |
| Vélib | cohérence | 13 `passed` |
| Vélib | volume | 8 `passed`, 5 `not_measured` |
| Vélib | fraîcheur | 1 `failed`, sévérité `error` |
| Trafic routier | schéma | 1 `passed` |
| Trafic routier | unicité | 1 `passed` |
| Trafic routier | cohérence | 5 `passed` |
| Trafic routier | volume | 5 `not_measured` |
| Trafic routier | fraîcheur | 1 `failed`, sévérité `error` |

Les deux incidents de fraîcheur sont cohérents avec l'environnement local : la
dernière exécution enregistrée date du 19 juillet 2026, alors que l'évaluation a
été réalisée le 22 juillet 2026. Ils ne signalent ni une erreur du connecteur ni
une défaillance actuelle de la production Mobility.

Après la suite de tests isolée, les données locales réelles sont restées
présentes : 18 exécutions, 42 contrôles et 2 incidents actifs.

## Limites maintenues

- les résultats dbt détaillés restent indisponibles faute de persistance côté
  Mobility ;
- le faible historique du trafic ne permet encore aucune mesure de volume ;
- les transitions opérateur sont disponibles dans le service métier mais ne
  seront exposées graphiquement qu'au Sprint 4 ;
- le blocage d'une publication nécessite un point de publication explicite et
  n'est pas simulé silencieusement dans ce sprint ;
- les incidents locaux de fraîcheur doivent être distingués de l'état futur de
  la source OVHcloud.
