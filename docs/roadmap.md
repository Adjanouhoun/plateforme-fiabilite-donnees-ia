# Feuille de route des sprints

Cette feuille de route décrit un ordre de réalisation. Chaque sprint commence
par un état des lieux et se termine par une preuve vérifiable, une documentation
et une décision explicite de clôture.

## Sprint 0 — Cadrage

### Objectif

Définir les frontières du POC, son contrat fonctionnel, ses risques et ses
critères de réussite.

### Preuve de clôture

- état des lieux relu ;
- contrat fonctionnel minimal validé ;
- architecture logique et ordre des sprints acceptés.

## Sprint 1 — Socle local et modèle commun

### Objectif

Créer l'environnement local minimal et le stockage des objets communs :
pipelines, exécutions, actifs, contrôles, incidents et dépendances.

### Preuve de clôture

- démarrage local reproductible ;
- migrations versionnées ;
- contraintes d'intégrité testées ;
- données de démonstration clairement identifiées comme telles.

## Sprint 2 — Connecteur Mobility en lecture seule

### Objectif

Mapper les métadonnées réellement disponibles dans Mobility vers le modèle
commun, sans modifier ses DAG ni ses données métier.

### Preuve de clôture

- mapping source-cible documenté ;
- collecte idempotente ;
- statuts et volumes rapprochés avec la source ;
- champs indisponibles explicitement signalés.

## Sprint 3 — Contrôles et incidents déterministes

### Objectif

Implémenter les règles de fraîcheur, volume, unicité, schéma et cohérence ainsi
que le cycle de vie minimal d'un incident.

### Preuve de clôture

- scénarios d'incident reproductibles ;
- preuves techniques historisées ;
- absence de mesure distinguée d'un contrôle réussi ;
- règles et sévérités documentées.

## Sprint 4 — Interface Streamlit multi-pipelines

### Objectif

Fournir une vue portefeuille et une vue détaillée reposant uniquement sur le
modèle commun.

### Preuve de clôture

- changement de pipeline sans changement d'application ;
- historique, contrôles et incidents consultables ;
- états vides et erreurs de source traités explicitement.

## Sprint 5 — Dépendances et impact

### Objectif

Présenter les dépendances prouvées entre actifs et relier un incident aux actifs
et indicateurs susceptibles d'être affectés.

### Preuve de clôture

- origine de chaque relation conservée ;
- aucune dépendance inventée en l'absence de preuve ;
- impact mesuré distingué de l'impact déclaré.

## Sprint 6 — Assistance IA contrôlée

### Objectif

Produire une explication d'incident à partir des faits enregistrés sans déléguer
à l'IA les décisions de qualité ou de publication.

### Preuve de clôture

- sources factuelles visibles ;
- protocole d'évaluation versionné ;
- comportement défini lorsque le service IA est indisponible ;
- aucune action irréversible déclenchée par le modèle.

## Sprint 7 — Second connecteur et portabilité

### Objectif

Connecter un pipeline de structure différente afin de tester la séparation entre
le cœur et les adaptateurs.

### Preuve de clôture

- second pipeline visible dans les vues existantes ;
- aucune règle métier du second pipeline ajoutée au cœur de l'interface ;
- écarts de contrat documentés ;
- preuve de portabilité acceptée.

## Sprint 8 — Qualification et déploiement OVHcloud

### Objectif

Mesurer le VPS, choisir le profil compact ou l'upgrade, sécuriser et déployer la
plateforme sans dégrader Mobility.

### Preuve de clôture

- mesures avant et après déploiement ;
- seuils de capacité vérifiés ;
- sauvegarde et restauration testées ;
- accès réseau et authentification revus ;
- procédure de retour arrière testée ;
- exploitation documentée.

## Règle d'arbitrage

Un composant n'est ajouté que s'il répond à un critère du POC qui ne peut pas
être satisfait plus simplement. Kafka, Marquez, Prometheus, Grafana et tout
service équivalent restent donc des options à justifier, et non des dépendances
acquises.
