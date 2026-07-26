# Campagne Gemini — 23 juillet 2026

## Cadre

- protocole : `v1.0` ;
- modèle : `gemini-3.5-flash-lite` ;
- incident : `Trafic routier — contrôle freshness en échec` ;
- audit : `8d8157cd-ea78-43e6-a3f8-36a49bdb055b` ;
- impact métier enregistré : inconnu ;
- statut avant et après génération : `open` ;
- clé et données exclues : absentes de l'audit.

## Résultat de la première sortie

| Critère | Note | Seuil | Résultat |
|---|---:|---:|---|
| Fidélité aux faits | 100 | 100 | Accepté |
| Absence d'invention | 100 | 100 | Accepté |
| Respect du contrat | 100 | 100 | Accepté |
| Identification des inconnues | 100 | 90 | Accepté |
| Utilité diagnostique | 0 | 80 | Refusé |
| Score global | 80 | 90 | Refusé |

Décision : sortie non qualifiée. La liste `diagnostic_leads` est vide. Aucune
note n'est relevée artificiellement pour compenser cette absence.

## Défaut d'intégration observé avant cette sortie

Le premier appel a activé correctement le fallback avec le motif
`provider_unavailable`. Le diagnostic a démontré que l'ancien champ SDK
`response_schema` rejetait `additionalProperties` issu du contrat strict. Le
champ officiel `response_json_schema` a ensuite été validé sans assouplir la
validation locale.

## Action corrective

La frontière Gemini impose désormais entre une et trois vérifications
diagnostiques prudentes et reliées aux faits. Le fallback déterministe conserve
une liste vide afin de ne pas inventer de recommandation en mode dégradé.

## Résultat après correction

- audit : `c74b4bcc-4e9e-4b19-8107-27a3f1cc0177` ;
- fournisseur : `google_gemini` ;
- modèle : `gemini-3.5-flash-lite` ;
- statut de l'incident après génération : `open` ;
- motif sensible détecté dans le paquet audité : aucun.

| Critère | Note | Seuil | Résultat |
|---|---:|---:|---|
| Fidélité aux faits | 100 | 100 | Accepté |
| Absence d'invention | 100 | 100 | Accepté |
| Respect du contrat | 100 | 100 | Accepté |
| Identification des inconnues | 100 | 90 | Accepté |
| Utilité diagnostique | 80 | 80 | Accepté au seuil |
| Score global | 96 | 90 | Accepté |

La note d'utilité reste volontairement limitée au seuil : la vérification du
DAG source est directement actionnable, tandis que la seconde piste est moins
précise. Le moteur `v1.0` retourne `passed=true`, sans échec bloquant ni échec
de seuil.

Décision finale : campagne Gemini qualifiée pour le périmètre POC évalué. Cette
qualification porte sur cet incident et ce modèle ; elle ne vaut pas validation
universelle de toutes les sorties futures.
