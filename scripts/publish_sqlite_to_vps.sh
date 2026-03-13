#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <server-ip-or-hostname> [ssh-key-path]"
  exit 1
fi

SERVER="$1"
KEY_PATH="${2:-$HOME/.ssh/muckrake_deploy}"
REMOTE_DB_PATH="/home/deploy/releases/muckrake.db"

if [ ! -f "data/muckrake.db" ]; then
  echo "Local SQLite database not found at data/muckrake.db"
  exit 1
fi

echo "[1/6] Upload local SQLite artifact"
ssh -i "$KEY_PATH" "deploy@$SERVER" "mkdir -p /home/deploy/releases"
rsync -az -e "ssh -i $KEY_PATH" "data/muckrake.db" "deploy@$SERVER:$REMOTE_DB_PATH"

echo "[2/6] Ensure pgloader is installed"
ssh -i "$KEY_PATH" "deploy@$SERVER" "sudo apt-get update && sudo apt-get install -y pgloader"

echo "[3/6] Replace production Postgres from SQLite artifact"
ssh -i "$KEY_PATH" "deploy@$SERVER" <<'EOSSH'
  set -e
  sudo systemctl stop muckrake-api
  sudo -u postgres dropdb --if-exists muckrake
  sudo -u postgres createdb --owner=muckrake muckrake
  set -a
  source /etc/muckrake/api.env
  set +a
  PG_URL=${MUCKRAKE_DATABASE_URL/+psycopg/}
  pgloader sqlite:///home/deploy/releases/muckrake.db "$PG_URL"
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d muckrake <<"SQL"
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE MATERIALIZED VIEW IF NOT EXISTS entity_search AS
SELECT
  s.canonical_id AS id,
  MIN(CASE WHEN s.prop = 'name' THEN s.value END) AS display_name,
  MIN(s.schema) AS schema,
  string_agg(DISTINCT s.value, ' ')
    FILTER (WHERE s.prop IN ('name', 'alias', 'previousName', 'weakAlias', 'abbreviation'))
    AS names_text,
  to_tsvector(
    'simple',
    unaccent(
      COALESCE(
        string_agg(DISTINCT s.value, ' ')
          FILTER (WHERE s.prop IN ('name', 'alias', 'previousName', 'weakAlias', 'abbreviation')),
        ''
      )
    )
  ) AS tsv
FROM statement AS s
WHERE s.schema IN ('Company', 'LegalEntity', 'Organization', 'Person', 'PublicBody')
  AND s.canonical_id IS NOT NULL
GROUP BY s.canonical_id;

CREATE UNIQUE INDEX IF NOT EXISTS entity_search_id_idx ON entity_search (id);
CREATE INDEX IF NOT EXISTS entity_search_tsv_idx ON entity_search USING GIN (tsv);
CREATE INDEX IF NOT EXISTS entity_search_display_name_trgm_idx ON entity_search USING GIN (display_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entity_search_names_text_trgm_idx ON entity_search USING GIN (names_text gin_trgm_ops);
ALTER MATERIALIZED VIEW entity_search OWNER TO muckrake;
GRANT SELECT ON entity_search TO muckrake;
REFRESH MATERIALIZED VIEW entity_search;
SQL
  sudo systemctl start muckrake-api
EOSSH

echo "[4/6] Ensure frontend service is healthy"
ssh -i "$KEY_PATH" "deploy@$SERVER" '
  set -e
  if ! sudo systemctl is-active --quiet openlobbying-web.service; then
    cd /home/deploy/muckrake/openlobbying
    npm ci
    npm run build
    sudo systemctl restart openlobbying-web.service
  fi
'

echo "[5/6] Verify row counts"
ssh -i "$KEY_PATH" "deploy@$SERVER" "sudo -u postgres psql -d muckrake -c \"select dataset, count(*) from statement group by dataset order by dataset;\" -c \"select count(*) from resolver;\" -c \"select count(*) from ner_candidates;\""

echo "[6/6] Check public endpoint"
curl -fsS -o /dev/null "https://openlobbying.org" && echo "Public site is up"

echo "Done"
echo "Open: https://openlobbying.org"
