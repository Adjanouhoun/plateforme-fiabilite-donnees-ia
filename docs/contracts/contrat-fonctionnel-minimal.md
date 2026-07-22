# Contrat fonctionnel minimal

## Finalité

Le POC doit démontrer qu'une même plateforme peut centraliser et présenter l'état
de plusieurs pipelines sans intégrer leur logique métier dans son cœur.

## Utilisateurs visés

Le premier POC distingue trois usages, sans implémenter immédiatement un système
complet de rôles :

- opérateur data : surveiller les exécutions et diagnostiquer les incidents ;
- responsable data : comparer la santé des pipelines et leur impact métier ;
- développeur de pipeline : intégrer un pipeline au moyen d'un connecteur documenté.

## Objets communs obligatoires

### Pipeline

- identifiant stable ;
- nom d'affichage ;
- description ;
- propriétaire déclaré ;
- environnement ;
- fréquence attendue ;
- criticité métier ;
- état d'activation.

### Exécution

- identifiant du pipeline ;
- identifiant externe de l'exécution ;
- heure de début et de fin ;
- statut normalisé ;
- volumes lus, écrits, rejetés ou inchangés lorsque disponibles ;
- message d'erreur assaini lorsque disponible.

### Actif de données

- identifiant stable ;
- type d'actif ;
- système et emplacement logique ;
- schéma ou contrat attendu ;
- propriétaire ;
- niveau de sensibilité déclaré.

### Contrôle de qualité

- identifiant et type de contrôle ;
- actif concerné ;
- sévérité ;
- valeur observée ;
- règle ou seuil attendu ;
- résultat ;
- horodatage ;
- preuve ou référence technique.

### Incident

- identifiant ;
- pipeline et actifs affectés ;
- contrôle déclencheur ;
- sévérité ;
- état ;
- heure d'ouverture et de clôture ;
- impact métier déclaré ou calculé ;
- historique des changements.

### Dépendance

- actif source ;
- actif cible ;
- type de transformation ;
- origine de la preuve de dépendance.

## Capacités minimales

### Vue portefeuille

L'utilisateur peut :

- voir tous les pipelines enregistrés ;
- comparer leur dernière exécution ;
- identifier les incidents ouverts ;
- filtrer par environnement, criticité et état.

### Vue d'un pipeline

L'utilisateur peut :

- sélectionner un pipeline sans changer d'application ;
- consulter son historique d'exécution ;
- consulter ses actifs et contrôles ;
- consulter ses incidents ;
- visualiser les dépendances disponibles ;
- distinguer les données mesurées des commentaires générés.

### Intégration

Un connecteur doit :

- lire une source autorisée ;
- convertir ses données vers les objets communs ;
- être idempotent ;
- conserver l'identifiant externe d'origine ;
- ne jamais exposer de secret dans les événements ou journaux ;
- déclarer explicitement les champs indisponibles ;
- échouer de manière visible si le contrat reçu est invalide.

## Règles de décision

- Un contrôle déterministe produit le statut de qualité.
- Une règle documentée détermine si une publication doit être bloquée.
- Une absence de mesure ne doit pas être transformée en résultat positif.
- Un score agrégé doit exposer sa formule et ses pondérations.
- Une explication IA ne peut pas modifier un statut, fermer un incident ou
  déclencher une remédiation sans validation explicite.

## Premier connecteur : Mobility

Le premier connecteur lira les métadonnées déjà disponibles dans les schémas de
monitoring et d'analyse de Mobility. Sa première version ne modifiera ni les DAG,
ni les modèles dbt, ni les données métier de Mobility.

Le mapping détaillé des colonnes sera défini au Sprint 2 après inspection du
schéma réel. Aucun mapping non vérifié n'est fixé dans ce document.

## Preuve de portabilité

La plateforme ne sera considérée comme multi-pipelines que si :

1. Mobility est visible et consultable dans Streamlit ;
2. un second pipeline de structure différente est intégré ;
3. les deux utilisent les mêmes objets communs et les mêmes vues ;
4. l'ajout du second pipeline ne nécessite pas de logique métier spécifique dans
   le cœur de l'interface.

## Critères de réussite du POC

- installation locale reproductible et documentée ;
- sélection d'au moins deux pipelines dans Streamlit ;
- ingestion idempotente de leurs métadonnées ;
- historique des exécutions et résultats qualité consultable ;
- incidents traçables depuis leur preuve technique ;
- détection démontrée d'un retard, d'un doublon, d'une rupture de schéma et d'une
  anomalie de volume sur les scénarios qui fournissent ces mesures ;
- blocage démontré d'une publication de test selon une règle documentée ;
- séparation visuelle entre résultats mesurés et explications IA ;
- tests automatisés des contrats et connecteurs ;
- absence de secrets dans le dépôt et les journaux ;
- documentation de déploiement et de retour arrière sur OVHcloud.

## Limites assumées

Le premier POC ne garantit pas :

- une disponibilité de niveau critique ;
- une remédiation autonome ;
- une compatibilité universelle ;
- une conservation illimitée des métriques ;
- une détection statistique pertinente sans historique suffisant ;
- une sécurité de production avant réalisation de la revue dédiée.
