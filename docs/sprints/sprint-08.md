# Sprint 8 — Qualification et déploiement OVHcloud

## Mesure initiale — 28 juillet 2026

Le VPS `vps-2f39f750` possède 4 vCores, 7,6 Go de mémoire et 72 Go de disque.
La mesure avant déploiement indique 4,9 Go de mémoire disponible, 47 Go de
disque libre et un swap déjà utilisé à 1,4 Go. Mobility, Superset et l'assistant
candidature emploi sont actifs ; aucun port publié ne conflictue avec le port
local 8501 proposé pour le dashboard de la plateforme.

## Décision de capacité

Le profil compact est retenu pour la première mise en ligne : PostgreSQL 384 Mo,
API 256 Mo et dashboard 512 Mo. Les collecteurs restent des tâches manuelles :
ils ne consomment aucune mémoire en permanence. Une évolution du VPS est
réexaminée si la mémoire disponible tombe durablement sous 1 Go ou si le swap
augmente pendant l'exploitation.

## Préparation

- sous-domaine retenu : `fiabilite.amadouadjanouhoun.fr` ;
- proxy Nginx versionné, prêt pour Certbot après propagation DNS ;
- secrets de production absents du dépôt ;
- démarrage limité à PostgreSQL, API et dashboard ;
- retour arrière : arrêt des trois services et suppression du site Nginx, sans
  toucher à Mobility ni à l'application emploi.

## Condition avant mise en ligne

Créer l'enregistrement DNS `A` de `fiabilite` vers `51.91.55.202`, puis
vérifier sa résolution publique avant de demander le certificat HTTPS.
