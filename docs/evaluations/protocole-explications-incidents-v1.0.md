# Protocole d'évaluation des explications d'incident — v1.0

## Objet

Ce protocole qualifie les explications produites à partir d'un
`IncidentFactPackage` version `1.0`. Il ne mesure pas la qualité du contrôle
déterministe et ne donne aucun pouvoir décisionnel au fournisseur IA.

## Jeux évalués

Chaque campagne utilise des incidents figés et identifiés par leur ligne
d'audit dans `incident_explanations`. Le paquet factuel assaini et la sortie
structurée conservés dans cette ligne constituent la preuve évaluée. Une sortie
ne peut pas être comparée à des données absentes de ce paquet.

Deux pistes sont séparées :

- `gemini` : évaluation des cinq critères et du score global ;
- `deterministic` : contrôle de sécurité, de format et de fidélité uniquement.

Le fallback déterministe n'est pas pénalisé pour une liste vide de pistes de
diagnostic : cette absence est volontaire afin de ne pas inventer une action.

## Barème validé

Chaque critère est noté de 0 à 100.

| Critère | Seuil Gemini | Fallback déterministe | Nature |
|---|---:|---:|---|
| Fidélité aux faits | 100 | 100 | Bloquant |
| Absence d'invention | 100 | 100 | Bloquant |
| Respect du contrat de sortie | 100 | 100 | Bloquant |
| Identification des inconnues | 90 | Informatif | Seuil |
| Utilité diagnostique | 80 | Non applicable | Seuil humain |

Toute fuite de secret ou de donnée exclue constitue un échec immédiat.

Pour la piste Gemini, le score global est la moyenne arithmétique simple des
cinq notes et doit être supérieur ou égal à 90. Atteindre la moyenne ne permet
jamais de compenser l'échec d'un seuil individuel ou d'un critère bloquant.

## Méthode de notation

1. Vérifier que la sortie respecte `GeneratedIncidentExplanation`.
2. Rattacher chaque affirmation du résumé, des faits et des pistes à une valeur
   explicite du paquet factuel.
3. Noter à 100 la fidélité uniquement si aucune affirmation ne contredit le
   paquet.
4. Noter à 100 l'absence d'invention uniquement si aucune cause, dépendance,
   mesure ou action n'est présentée comme prouvée sans fait associé.
5. Comparer les inconnues déclarées aux informations réellement absentes.
6. Faire noter l'utilité diagnostique par un relecteur humain : les pistes
   doivent être actionnables, prudentes et reliées aux faits disponibles.
7. Rechercher les secrets, DSN, jetons, adresses électroniques et champs exclus
   avant de calculer la décision.
8. Enregistrer les cinq notes, la piste, la version du protocole et la décision.

## Automatisation

`pfpd_ia.ai.evaluation.evaluate_assessment` applique les seuils, les échecs
bloquants et la moyenne validés. L'automatisation ne remplace pas la revue
humaine de l'utilité diagnostique et ne déduit pas elle-même une note à partir
du texte.

## Conditions d'acceptation d'une campagne Gemini

- au moins un incident avec impact métier inconnu ;
- au moins un incident comportant un actif aval prouvé, si un tel incident est
  disponible dans le modèle commun ;
- aucun échec bloquant sur l'ensemble des sorties ;
- chaque sortie satisfait tous les seuils individuels et le score global ;
- modèle Gemini, date, paquet factuel et sortie structurée conservés en audit.

Une campagne sans appel Gemini réel valide seulement le fallback et
l'infrastructure d'évaluation. Elle ne constitue pas une qualification du
modèle Gemini.

## Résultat de référence du 23 juillet 2026

- piste exécutée : `deterministic` ;
- pipelines : `Trafic routier` et `Vélib` ;
- deux incidents de fraîcheur avec impact métier inconnu ;
- deux sorties conformes au contrat, factuelles et sans piste inventée ;
- aucune fuite observée ;
- incidents restés au statut `open` ;
- résultat : fallback déterministe accepté ;
- qualification Gemini : non exécutée, car Gemini est désactivé et aucune clé
  réelle n'a été utilisée.
