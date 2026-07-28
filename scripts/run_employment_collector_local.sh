#!/usr/bin/env bash
set -euo pipefail

source_container="${EMPLOYMENT_SOURCE_CONTAINER:-assistant-candidature-emploi-ia-postgres-1}"
platform_network="${PLATFORM_DOCKER_NETWORK:-plateforme-fiabilite-donnees-ia_default}"
keychain_service="pfpd-ia-employment-reader-local"

if ! docker inspect "$source_container" >/dev/null 2>&1; then
  echo "Conteneur PostgreSQL emploi introuvable : $source_container" >&2
  exit 1
fi

if ! docker network inspect "$platform_network" \
  --format '{{range .Containers}}{{.Name}} {{end}}' | grep -Fq "$source_container"; then
  docker network connect "$platform_network" "$source_container"
fi

reader_password="$(security find-generic-password -a employment_reader -s "$keychain_service" -w)"
export EMPLOYMENT_DATABASE_URL="postgresql+psycopg://employment_reader:${reader_password}@${source_container}:5432/app"
trap 'unset EMPLOYMENT_DATABASE_URL reader_password' EXIT

docker compose --profile tools run --rm employment_collector
