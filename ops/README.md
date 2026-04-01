# Deployment

- `ops/deploy_to_vps.sh`: deploy the application code to an already provisioned server.
- `ops/systemd/`: `systemd` unit templates for the API and frontend.
- `ops/caddy/openlobbying.org.Caddyfile`: Caddy site config for the app.
- `ops/hetzner/`: optional Hetzner bootstrap templates.

## Deployment conventions

- Production DB is configured via `MUCKRAKE_DATABASE_URL` and `MUCKRAKE_PUBLISHED_DATABASE_URL`.
- Production publishing uses one curated DB artifact and must preserve resolver and NER candidate state.
- Frontend calls backend through relative `/api/*` routes.
- Local frontend development proxies `/api` to `http://127.0.0.1:8000`.
- Secrets stay on the server, never in git.

## App deploy

For routine application updates, run:

```bash
./ops/deploy_to_vps.sh <server-ip-or-hostname> [ssh-key-path]
```

This script:

1. Syncs the repository contents to `/home/deploy/muckrake/`.
2. Runs `uv sync`, `npm ci`, and `npm run build` on the server.
3. Restarts `muckrake-api`, `openlobbying-web`, and `caddy`.

The script assumes the server is already provisioned with runtime packages, env files, and installed service definitions.

## One-server VPS setup

This setup is tested on one Hetzner VPS running Ubuntu 24.04 with:

- Caddy for HTTPS and reverse proxy
- FastAPI backend as a `systemd` service
- SvelteKit frontend (`adapter-node`) as a `systemd` service
- PostgreSQL 16 on the same VPS

## Hetzner bootstrap

Optional bootstrap templates live in `ops/hetzner/`:

- `cloud-init.example.yaml`
- `firewall-rules.json`

Recommended server options:

- Image: Ubuntu 24.04
- Type: CPX22
- Location: NBG1
- Networking: IPv4 and IPv6 enabled
- SSH key: add your public key

If using cloud-init, replace the placeholder SSH key before creating the server.

Optional CLI firewall setup:

```bash
hcloud firewall create --name "muckrake-web" --rules-file "ops/hetzner/firewall-rules.json"
hcloud firewall apply-to-resource --type server --server "muckrake-prod-01" "muckrake-web"
```

## Runtime packages

Install the runtime packages on the server:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git caddy postgresql postgresql-contrib rsync
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install -y build-essential pkg-config libicu-dev libleveldb-dev
```

## Database setup

Create the role and databases:

```bash
sudo -u postgres psql -c "CREATE ROLE muckrake LOGIN PASSWORD '<strong-password>';"
sudo -u postgres psql -c "CREATE DATABASE muckrake OWNER muckrake;"
sudo -u postgres psql -c "CREATE DATABASE muckrake_published OWNER muckrake;"
```

## Install service and proxy configs

Copy templates into system locations:

```bash
sudo mkdir -p /etc/muckrake
sudo cp /home/deploy/muckrake/ops/systemd/muckrake-api.service /etc/systemd/system/
sudo cp /home/deploy/muckrake/ops/systemd/openlobbying-web.service /etc/systemd/system/
sudo cp /home/deploy/muckrake/ops/caddy/openlobbying.org.Caddyfile /etc/caddy/Caddyfile
```

Create `/etc/muckrake/api.env`:

```env
MUCKRAKE_DATABASE_URL=postgresql+psycopg://muckrake:<password>@127.0.0.1:5432/muckrake
MUCKRAKE_PUBLISHED_DATABASE_URL=postgresql+psycopg://muckrake:<password>@127.0.0.1:5432/muckrake_published
MUCKRAKE_DATA_PATH=/var/lib/muckrake/data
MUCKRAKE_ARTIFACT_PATH=/var/lib/muckrake/data/artifacts
ENVIRONMENT=production
```

Create `/etc/muckrake/web.env`:

```env
HOST=127.0.0.1
PORT=3000
ORIGIN=https://openlobbying.org
NODE_ENV=production
AUTH_SECRET=<strong-random-secret>
```

Enable and start the services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now muckrake-api openlobbying-web caddy
```

## Verification

```bash
curl -I https://openlobbying.org
curl https://openlobbying.org/api/datasets
curl "https://openlobbying.org/api/search?q=global%20counsel&limit=5"
curl "https://openlobbying.org/api/search?q=whitehouse%20communications&limit=5"
```

## Operations notes

- Restrict the SSH firewall rule to your IP after bootstrap.
- Restart services after config changes with `sudo systemctl restart muckrake-api openlobbying-web caddy`.
- Keep app-specific config in this repository and keep server-local secrets in `/etc/muckrake/*.env`.
