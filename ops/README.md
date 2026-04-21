# Deployment

- `ops/deploy_to_vps.sh`: app deploy script.
- `ops/systemd/`: service templates.
- `ops/caddy/openlobbying.org.Caddyfile`: reverse proxy config.
- `ops/hetzner/`: Hetzner bootstrap notes and templates.

Production env must live on the server under `/etc/muckrake/`.

- `/etc/muckrake/api.env` should define `MUCKRAKE_DATABASE_URL`, `MUCKRAKE_PUBLISHED_DATABASE_URL`, and `AUTH_SECRET`.
- `/etc/muckrake/web.env` should define `HOST`, `PORT`, `ORIGIN`, `NODE_ENV`, `MUCKRAKE_DATABASE_URL`, `AUTH_SECRET`, and `BETTER_AUTH_URL`.
- `deploy_to_vps.sh` intentionally does not sync local `.env` files to the VPS.

For the full runbook, see `ops/hetzner/README.md`.
