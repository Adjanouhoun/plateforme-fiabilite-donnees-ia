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

## Mise en ligne — 28 juillet 2026

L'enregistrement DNS `fiabilite.amadouadjanouhoun.fr` a été résolu vers
`51.91.55.202`, puis le déploiement issu de la révision `3b31f69` a été réalisé
dans `/home/ubuntu/plateforme-fiabilite-donnees-ia`.

- PostgreSQL, l'API et le dashboard sont démarrés, avec leurs contrôles de
  santé au vert ;
- l'API confirme l'accès à PostgreSQL via `/health/ready` ;
- seul Nginx expose l'interface : les ports des services restent liés à
  `127.0.0.1` sur le VPS ;
- Nginx redirige HTTP vers HTTPS ;
- le certificat Let's Encrypt de `fiabilite.amadouadjanouhoun.fr` est installé,
  expire le 26 octobre 2026 et son renouvellement automatique est activé ;
- l'accès public validé est : `https://fiabilite.amadouadjanouhoun.fr`.

## Contrôle après déploiement

La consommation instantanée des services de la plateforme reste contenue :

- API : environ 71 Mo sur une limite de 256 Mo ;
- dashboard : environ 48 Mo sur une limite de 512 Mo ;
- PostgreSQL : environ 61 Mo sur une limite de 384 Mo.

Le profil compact est donc adapté à la cohabitation actuelle avec Mobility et
l'assistant candidature emploi. Aucun redimensionnement du VPS n'est requis à
ce stade.

## Exploitation et retour arrière

Pour mettre à jour la plateforme, récupérer la révision voulue dans le dossier
de déploiement puis redémarrer uniquement les services de ce projet avec le
fichier `deploy/ovh/docker-compose.prod.yml`. Les secrets de production restent
dans le fichier `.env` du VPS, non versionné.

En cas de retour arrière, arrêter les trois services de la plateforme et
restaurer la révision Git précédente. Les conteneurs, bases et configurations
de Mobility et de l'assistant emploi ne doivent pas être modifiés.
