# Plateforme de Fiabilité et de Préparation des Données pour l'IA

Plateforme centralisée destinée à surveiller plusieurs pipelines de données,
contrôler leur fiabilité, historiser leurs incidents et évaluer leur aptitude à
alimenter des usages analytiques ou d'intelligence artificielle.

Le projet est actuellement dans sa phase de cadrage. Aucun composant de
production n'est encore implémenté.

## Principes directeurs

- cœur indépendant des pipelines supervisés ;
- intégration par connecteurs et contrats communs ;
- contrôles déterministes et auditables ;
- séparation entre faits mesurés et explications produites par l'IA ;
- développement et validation en local avant déploiement sur OVHcloud ;
- dimensionnement de la production fondé sur des mesures réelles.

## Documentation

- [Sprint 0 — État des lieux et cadrage](docs/sprints/sprint-00.md)
- [Contrat fonctionnel minimal](docs/contracts/contrat-fonctionnel-minimal.md)
- [Feuille de route des sprints](docs/roadmap.md)
