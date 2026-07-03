#!/bin/bash
# Create the published (read-only API) database alongside the app database.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE DATABASE ${POSTGRES_DB}_published OWNER "$POSTGRES_USER";
EOSQL
