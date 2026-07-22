# Sprint 0 — État des lieux et cadrage

## Statut

Clôturé le 22 juillet 2026.

Le cadrage, le contrat fonctionnel minimal, l'architecture logique et l'ordre
des sprints ont été validés par le porteur du projet.

## Objectif

Définir le périmètre vérifiable du POC avant toute implémentation et établir les
conditions de son développement local puis de son déploiement sur la VM
OVHcloud.

## Sources examinées

- dépôt `plateforme-fiabilite-donnees-ia` ;
- dépôt local `data-pipeline-mobility` ;
- branche `ops/ovh-production-deployment` du pipeline Mobility ;
- documentation générale et documentation du Sprint 13 de Mobility ;
- fichiers Docker Compose local et production de Mobility ;
- caractéristiques OVHcloud communiquées pour la VM cible.

## État initial du nouveau dépôt

Au démarrage du Sprint 0 :

- le dépôt ne contenait qu'un fichier `README.md` avec son titre ;
- aucun service, modèle de données ou connecteur n'était implémenté ;
- la branche `main` était synchronisée avec `origin/main` ;
- le cadrage a été isolé sur la branche `docs/sprint-00-cadrage`.

## Premier pipeline de référence

Le premier système supervisé sera `data-pipeline-mobility`.

### Composants vérifiés

- Apache Airflow 2.9.1 avec `LocalExecutor` ;
- dbt Core et dbt PostgreSQL 1.7.19 ;
- PostgreSQL 15 ;
- Apache Superset 4.0.1 ;
- pgAdmin ;
- Docker Compose ;
- deux pipelines horaires : Vélib et trafic routier parisien.

### Métadonnées déjà disponibles

Le pipeline Mobility expose déjà des informations utiles dans son entrepôt :

- `schema_monitoring.ingestion_runs` ;
- `schema_monitoring.traffic_ingestion_runs` ;
- `schema_analytics.fct_ingestion_runs` ;
- `schema_analytics.fct_traffic_ingestion_runs` ;
- `schema_analytics.fct_pipeline_runs` ;
- exécution de contrôles dbt par les DAG.

Ces éléments permettent un premier branchement en lecture seule sans modifier
immédiatement l'orchestration existante.

La persistance et l'exposition du détail des résultats dbt ne sont pas encore
établies. Elles devront être vérifiées avant de définir leur mapping.

## Contraintes de production connues

La VM OVHcloud cible est un modèle VPS-2 actuellement décrit comme disposant de :

- 4 vCœurs ;
- 8 Go de mémoire vive ;
- 75 Go de stockage ;
- un déploiement existant de `data-pipeline-mobility`.

Une évolution vers 8 cœurs et 16 Go de mémoire vive est possible si les mesures
d'exploitation la justifient.

Le déploiement Mobility déclare actuellement les services permanents suivants :

- trois instances PostgreSQL ;
- Airflow Webserver ;
- Airflow Scheduler ;
- Superset ;
- pgAdmin.

La capacité résiduelle réelle de la VM n'a pas encore été mesurée. Il est donc
interdit de conclure à ce stade que la pile complète d'observabilité peut y être
hébergée simultanément.

## Décisions validées

1. Le produit sera indépendant du pipeline Mobility.
2. Mobility sera le premier pipeline de référence, pas une dépendance structurelle.
3. Le premier connecteur fonctionnera en lecture seule.
4. Streamlit proposera une vue portefeuille et une vue par pipeline.
5. Les règles de qualité et de blocage resteront déterministes.
6. L'IA pourra expliquer un incident, mais ne décidera pas seule de la validité
   ou de la publication des données.
7. Le développement et les tests seront réalisés localement avant la production.
8. Le déploiement OVH initial sera compact et fondé sur les mesures de capacité.
9. Un second pipeline devra être connecté avant de déclarer la plateforme générique.

## Architecture logique retenue

```text
Pipelines supervisés
        │
        ▼
Connecteurs spécifiques
        │
        ▼
Contrat commun d'observabilité
        │
        ▼
Stockage central des métadonnées
        │
        ├── moteur de règles et incidents
        └── historique et indicateurs
                    │
                    ▼
           Interface Streamlit
```

La sélection d'un pipeline dans Streamlit filtrera les mêmes objets communs :
exécutions, actifs de données, contrôles, incidents et dépendances.

## Stratégie de capacité OVH

Le profil initial doit privilégier un collecteur léger, un stockage central et
Streamlit. Les composants plus lourds tels que Kafka, Marquez, Prometheus ou
Grafana ne seront ajoutés qu'après justification fonctionnelle et mesure de leur
impact.

Une montée en capacité sera examinée si au moins un des symptômes suivants est
observé sur une période représentative :

- mémoire durablement supérieure à 70–75 % ;
- utilisation régulière du swap ;
- redémarrage d'un conteneur par manque de mémoire ;
- ralentissement significatif d'Airflow, dbt ou Superset lors des traitements ;
- contention CPU récurrente pendant les fenêtres d'orchestration ;
- occupation disque supérieure à 70 % malgré la politique de rétention.

Ces seuils déclenchent une analyse et non un upgrade automatique.

## Informations encore inconnues

Les points suivants doivent être mesurés ou décidés avant la production :

- système d'exploitation et architecture réellement rapportée par la VM ;
- consommation CPU, mémoire, swap et disque du déploiement Mobility ;
- capacité résiduelle pendant une exécution Airflow/dbt ;
- politique d'accès réseau entre la plateforme et Mobility ;
- domaine, terminaison TLS et méthode d'authentification de Streamlit ;
- emplacement définitif du stockage central d'observabilité ;
- identité et caractéristiques du second pipeline de validation.

## Hors périmètre du premier POC

- remplacement de l'orchestrateur Mobility ;
- modification automatique des données sources ;
- remédiation autonome par IA ;
- compatibilité immédiate avec tous les orchestrateurs et stockages ;
- streaming temps réel sans cas d'usage validé ;
- déploiement Kubernetes ;
- haute disponibilité multi-nœuds.

## Livrables attendus du Sprint 0

- état des lieux vérifiable ;
- contrat fonctionnel minimal ;
- architecture logique ;
- liste des inconnues et risques ;
- critères d'acceptation du futur POC ;
- plan de sprints proposé et validé.

## Critères de clôture

Le Sprint 0 pourra être clôturé lorsque :

1. le contrat fonctionnel minimal aura été relu et validé ;
2. les frontières entre plateforme générique et connecteurs seront acceptées ;
3. les critères de réussite du POC seront acceptés ;
4. l'ordre des sprints de réalisation sera validé ;
5. aucune information inconnue ne bloquera le développement local du Sprint 1.
