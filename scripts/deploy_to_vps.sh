#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <server-ip-or-hostname> [ssh-key-path]"
  exit 1
fi

SERVER="$1"
KEY_PATH="${2:-$HOME/.ssh/muckrake_deploy}"

echo "[1/4] Sync code to VPS"
rsync -az --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "data" \
  --exclude "openlobbying/node_modules" \
  -e "ssh -i $KEY_PATH" \
  ./ "deploy@$SERVER:/home/deploy/muckrake/"

echo "[2/4] Install deps, build frontend, restart services"
ssh -i "$KEY_PATH" "deploy@$SERVER" '
  set -e
  cd /home/deploy/muckrake
  /home/deploy/.local/bin/uv sync
  cd /home/deploy/muckrake/openlobbying
  npm ci
  npm run build
  sudo systemctl restart muckrake-api openlobbying-web caddy
'

echo "[3/4] Publish local curated SQLite state to Postgres"
"$(dirname "$0")/publish_sqlite_to_vps.sh" "$SERVER" "$KEY_PATH"

echo "[4/4] Done"
echo "Open: https://openlobbying.org"
