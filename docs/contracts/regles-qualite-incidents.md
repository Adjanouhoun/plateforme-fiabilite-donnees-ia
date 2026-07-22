# Contrat des contrôles de qualité et incidents

## Portée

Ce contrat définit les règles déterministes du Sprint 3. Il s'applique au cœur
de la plateforme ; un connecteur fournit les mesures et les références de
preuve sans redéfinir le sens des statuts.

## Statuts

- `passed` : la mesure disponible respecte la règle ;
- `failed` : la mesure disponible enfreint la règle ;
- `not_measured` : les données nécessaires ne sont pas disponibles ou
  l'historique minimal n'est pas atteint.

`not_measured` ne doit jamais fermer un incident ni être agrégé comme un
succès.

## Contrôles

### Fraîcheur

La mesure est l'âge de la dernière exécution réussie, calculé depuis son heure
de fin jusqu'à l'heure d'évaluation.

| Âge | Statut | Sévérité |
|---|---|---|
| jusqu'à 120 minutes incluses | `passed` | `warning` |
| plus de 120 à 360 minutes incluses | `failed` | `warning` |
| plus de 360 minutes | `failed` | `error` |
| aucune exécution réussie | `not_measured` | `warning` |

### Volume

Le volume courant est comparé à la médiane des cinq exécutions réussies qui le
précèdent. La valeur courante est exclue de sa propre référence.

- écart absolu supérieur à 50 % : `failed` ;
- écart inférieur ou égal à 50 % : `passed` ;
- moins de cinq références, volume absent ou exécution courante non réussie :
  `not_measured`.

Si la médiane vaut zéro, seul un volume courant nul est conforme.

### Unicité

Le contrôle compare le nombre total d'exécutions source au nombre
d'identifiants `pipeline_run_id` distincts pour chaque DAG.

- différence nulle : `passed` ;
- au moins un doublon : `failed` de sévérité `error` ;
- source non mesurable : `not_measured`.

### Cohérence des volumes

La règle est :

```text
rows_read = rows_written + rows_unchanged
```

Une différence produit `failed` de sévérité `error`. L'absence d'un opérande
produit `not_measured`.

### Schéma

Le connecteur compare les colonnes requises et leurs types PostgreSQL
compatibles au contrat source. Une colonne manquante ou incompatible produit un
échec `error`. Les colonnes supplémentaires sont admises.

En cas d'échec, le connecteur n'exécute pas la requête de collecte incompatible.

## Idempotence

- schéma, unicité et fraîcheur : une mesure par pipeline et créneau UTC d'une
  heure ;
- volume et cohérence : une mesure par identifiant externe d'exécution ;
- unicité SQL cible : `(pipeline_id, idempotency_key)`.

Une répétition du même contrôle ne crée ni nouvelle mesure ni nouvel événement
d'incident.

## Incidents

La clé active associe l'actif et le type de contrôle. Un index PostgreSQL unique
partiel interdit deux incidents `open` ou `acknowledged` portant cette même clé.

| Événement | État initial | État final | Acteur |
|---|---|---|---|
| premier échec | aucun | `open` | moteur de qualité |
| nouvel échec | `open` ou `acknowledged` | inchangé | moteur de qualité |
| acquittement | `open` | `acknowledged` | opérateur explicite |
| retour conforme | `open` ou `acknowledged` | `resolved` | moteur de qualité |
| clôture | `resolved` | `closed` | opérateur explicite |

Un incident résolu ou clos n'empêche pas l'ouverture d'un nouvel incident lors
d'une rechute ultérieure. Chaque transition est ajoutée à `incident_events`.

## Preuves et confidentialité

Les preuves contiennent uniquement des nombres, horodatages, noms de colonnes,
types attendus et références logiques d'actifs. Elles ne contiennent ni données
métier, ni chaîne de connexion, ni message d'erreur source brut.
