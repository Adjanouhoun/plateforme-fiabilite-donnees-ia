# Sprint 4 — Interface Streamlit multi-pipelines

## Statut

État des lieux et cadrage validés le 22 juillet 2026. Implémentation terminée,
en attente de validation utilisateur avant commit et publication.

## Objectif

Fournir une interface locale en français permettant de comparer les pipelines,
d'en sélectionner un sans changer d'application et de consulter uniquement les
faits présents dans le modèle commun.

## État des lieux

- aucun écran métier n'existe ;
- l'API FastAPI expose uniquement les endpoints de santé ;
- le stockage commun contient 2 pipelines, 18 exécutions, 2 actifs, 42
  contrôles et 2 incidents ;
- aucune relation de lineage n'est encore disponible ;
- aucun impact métier n'est mesuré ou déclaré ;
- les transitions d'acquittement et de clôture sont disponibles dans le service
  métier du Sprint 3 ;
- Streamlit n'était pas encore une dépendance du projet.

## Décisions validées

- Streamlit 1.59.2 sur Python 3.11 ;
- service Docker indépendant, exposé localement sur `127.0.0.1:8501` ;
- interface et libellés en français ;
- vue portefeuille et vue détaillée dans la même application ;
- sélection du pipeline sans logique Mobility dans le cœur de l'interface ;
- actualisation manuelle ;
- aucun score agrégé opaque ;
- état synthétique fondé uniquement sur l'incident actif le plus sévère ;
- tableaux interactifs natifs Streamlit ;
- actions d'incident autorisées uniquement si `OPERATOR_NAME` est configuré ;
- mode lecture seule lorsque l'identité opérateur est absente ;
- authentification de production reportée à la qualification OVHcloud.

## Règle d'état synthétique

| Faits observés | État affiché |
|---|---|
| incident actif `critical` ou `error` | Incident majeur |
| incident actif `warning` | Avertissement |
| aucune exécution | Sans données |
| aucun incident actif et au moins une exécution | Sain |

Cet état ne remplace pas les contrôles détaillés et n'utilise aucune pondération
cachée.

## Écrans

### Portefeuille

- nombre de pipelines ;
- incidents actifs ;
- contrôles en échec et non mesurés ;
- filtres par environnement, criticité et état ;
- dernière exécution et volumes disponibles par pipeline.

### KPI temporels validés

La vue portefeuille propose une fenêtre de 7 ou 30 jours et affiche :

- taux de réussite : exécutions `succeeded` divisées par les exécutions dont
  `ended_at` est renseigné ;
- taux de conformité : contrôles `passed` divisés par les contrôles mesurés
  (`passed`, `failed`), en excluant `not_measured` ;
- retard maximal : maximum de `age_minutes` parmi les contrôles `freshness`
  mesurés ;
- incidents actuellement actifs, répartis entre `critical`, `error`, `warning`
  et `info` ;
- durée moyenne des incidents clôturés dans la fenêtre, calculée par
  `closed_at - opened_at` ;
- tendance par comparaison avec la fenêtre précédente de même durée.

Une absence de dénominateur ou de mesure produit `Non mesuré`, jamais zéro.

### Détail d'un pipeline

- identité, propriétaire, environnement, criticité et fréquence ;
- historique des exécutions ;
- contrôles et preuves structurées ;
- incidents et événements ;
- actifs techniques ;
- dépendances avec état vide explicite.

## Actions opérateur

- `open` peut être acquitté ;
- `resolved` peut être clôturé ;
- les autres transitions restent déterminées par le moteur du Sprint 3 ;
- chaque action affiche son résultat et conserve l'acteur configuré ;
- aucune action n'est disponible si `OPERATOR_NAME` est vide.

## Architecture retenue

Streamlit utilise une couche de requêtes SQLAlchemy dédiée au modèle commun. Il
ne lit pas directement Mobility et ne réimplémente pas les règles de qualité.
Les mutations d'incident appellent le service métier existant.

L'ajout d'endpoints FastAPI métier n'est pas nécessaire pour démontrer le POC
local et introduirait une seconde couche de contrat sans besoin validé.

## États vides et erreurs

- absence de pipeline : écran explicite, sans métrique trompeuse ;
- absence de contrôle, incident, actif ou dépendance : message dédié ;
- valeur non mesurée : libellé `Non mesuré`, jamais `Conforme` ;
- base indisponible : erreur utilisateur concise sans chaîne de connexion ;
- impact inconnu : libellé explicite, sans texte généré.

## Hors périmètre

- authentification et autorisation de production ;
- création ou modification des règles ;
- collecte Mobility depuis l'interface ;
- graphe de lineage inventé en l'absence de preuve ;
- explications IA ;
- déploiement OVHcloud.

## Critères de clôture

- changement de pipeline sans rechargement d'une autre application ;
- portefeuille et détail alimentés exclusivement par le modèle commun ;
- filtres et états vides vérifiés ;
- `not_measured` visuellement distinct ;
- incidents et historique consultables ;
- actions opérateur protégées par la configuration ;
- tests automatisés et contrôle visuel dans le navigateur ;
- démarrage Docker et endpoint de santé validés ;
- documentation locale mise à jour.

## Vérifications réalisées le 22 juillet 2026

- image Docker construite avec Streamlit 1.59.2 et Python 3.11 ;
- services `postgres_observability` et `dashboard` déclarés sains par Docker ;
- endpoint `http://127.0.0.1:8501/_stcore/health` : réponse `ok` ;
- suite automatisée complète : 28 tests réussis ;
- formatage et analyse statique : réussis ;
- contrôle navigateur réel des KPI sur les fenêtres de 7 et 30 jours : réussi ;
- valeurs observées sur les données locales : réussite 100,0 %, conformité
  93,8 %, retard maximal 4,0 jours, 2 incidents actifs (`error`) et durée
  moyenne de clôture `Non mesuré` ;
- comparaison affichée avec la fenêtre précédente de même durée et changement
  effectif du sélecteur de 7 à 30 jours : vérifiés ;
- contrôle navigateur réel du portefeuille : 2 pipelines, 2 incidents actifs,
  2 contrôles en échec et 10 contrôles non mesurés ;
- navigation réelle vers la fiche `Trafic routier` et ses quatre onglets :
  réussie ;
- présence de cinq contrôles `Non mesuré` pour le pipeline sélectionné :
  vérifiée ;
- incident `freshness` affiché avec impact métier inconnu et actions masquées en
  l'absence de `OPERATOR_NAME` : vérifié ;
- absence de lineage rendue par un état vide explicite, sans graphe inventé :
  vérifiée ;
- aucune mutation d'incident effectuée durant la validation visuelle.

## Résultat

Le Sprint 4 satisfait ses critères techniques et fonctionnels locaux. La
qualification de l'authentification et le déploiement OVHcloud restent hors de
ce sprint, conformément au cadrage validé.
