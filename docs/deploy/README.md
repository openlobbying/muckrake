# VPS deployment guide

This is the complete guide to deploy Muckrake + OpenLobbying on one Hetzner VPS.

## Day-to-day updates (recommended)

From local repo root, run one command:

```bash
./scripts/deploy_to_vps.sh {ip_address}
```

This will:

1. Sync latest code to VPS.
2. Install deps, build frontend, restart services.

## What this setup uses

- One VPS (tested on Hetzner `CPX22`, Ubuntu 24.04).
- Caddy for HTTPS and reverse proxy.
- FastAPI backend as a `systemd` service.
- SvelteKit frontend (`adapter-node`) as a `systemd` service.
- PostgreSQL 16 on the same VPS.

## Files in this directory

- `cloud-init-hetzner.yaml`: first-boot hardening and base packages.
- `SSH.md`: step-by-step SSH connection setup for the VPS.
- `hetzner-firewall-rules.json`: inbound `22/80/443` firewall policy.
- `Caddyfile`: `openlobbying.org` reverse proxy config.
- `muckrake-api.service`: backend unit.
- `openlobbying-web.service`: frontend unit.

If SSH access is failing or you need to recover console access, start with `docs/deploy/SSH.md`.

## 1) Create the server

Recommended options:

- Image: Ubuntu 24.04.
- Type: CPX22.
- Location: NBG1.
- Networking: IPv4 + IPv6 enabled.
- SSH key: add your key.
- Cloud config: paste `cloud-init-hetzner.yaml` after replacing the placeholder key.

To set up SSH for the deploy scripts:

1. Generate a key if you do not already have one:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/muckrake_deploy -C "deploy@muckrake"
```

2. Copy the public key into Hetzner Cloud, or append it to `/home/deploy/.ssh/authorized_keys` on the server:

```bash
cat ~/.ssh/muckrake_deploy.pub
```

3. Use the private key with the scripts:

```bash
./scripts/deploy_to_vps.sh {ip_address} ~/.ssh/muckrake_deploy
```

Optional CLI firewall setup:

```bash
hcloud firewall create --name "muckrake-web" --rules-file "docs/deploy/hetzner-firewall-rules.json"
hcloud firewall apply-to-resource --type server --server "muckrake-prod-01" "muckrake-web"
```

## 2) Point DNS to the server

At your DNS provider:

- `A` record: `@ -> <server-ipv4>`
- `A` record: `www -> <server-ipv4>`

## 3) Install runtime packages on VPS

```bash
sudo apt update
sudo apt install -y ca-certificates curl git caddy postgresql postgresql-contrib rsync
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install backend native build deps:

```bash
sudo apt install -y build-essential pkg-config libicu-dev libleveldb-dev
```

## 4) Deploy code

Copy code from your machine to the server (example path):

```bash
rsync -az --delete \
  --exclude ".git" --exclude ".venv" --exclude "data" --exclude "openlobbying/node_modules" \
  ./ deploy@<server-ip>:/home/deploy/muckrake/
```

Build on the server:

```bash
cd /home/deploy/muckrake
~/.local/bin/uv sync
cd /home/deploy/muckrake/openlobbying
npm ci
npm run build
```

## 5) Configure PostgreSQL

Create role and DB:

```bash
sudo -u postgres psql -c "CREATE ROLE muckrake LOGIN PASSWORD '<strong-password>';"
sudo -u postgres psql -c "CREATE DATABASE muckrake OWNER muckrake;"
```

## 6) Install service and proxy configs

Copy templates to system locations:

```bash
sudo mkdir -p /etc/muckrake
sudo cp /home/deploy/muckrake/docs/deploy/muckrake-api.service /etc/systemd/system/
sudo cp /home/deploy/muckrake/docs/deploy/openlobbying-web.service /etc/systemd/system/
sudo cp /home/deploy/muckrake/docs/deploy/Caddyfile /etc/caddy/Caddyfile
```

Create env files:

`/etc/muckrake/api.env`

```env
MUCKRAKE_DATABASE_URL=postgresql+psycopg://muckrake:<password>@127.0.0.1:5432/muckrake
MUCKRAKE_DATA_PATH=/var/lib/muckrake/data
ENVIRONMENT=production
```

`/etc/muckrake/web.env`

```env
HOST=127.0.0.1
PORT=3000
ORIGIN=https://openlobbying.org
NODE_ENV=production
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now muckrake-api openlobbying-web caddy
```

## 7) Quick verification

```bash
curl https://openlobbying.org/api/datasets
curl "https://openlobbying.org/api/search?q=global%20counsel&limit=5"
curl "https://openlobbying.org/api/search?q=whitehouse%20communications&limit=5"
```

## 8) Smoke tests

```bash
curl -I https://openlobbying.org
curl https://openlobbying.org/api/datasets
```

## Operations notes

- The app requires `MUCKRAKE_DATABASE_URL`.
- Frontend calls backend via relative `/api/*` routes.
- Secrets stay on server (`/etc/muckrake/*.env`), never in git.
- After bootstrap, restrict SSH firewall rule to your IP.
- Restart services after deploy:

```bash
sudo systemctl restart muckrake-api openlobbying-web caddy
```
