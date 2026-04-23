# Deployment

- `ops/deploy_to_vps.sh`: app deploy script.
- `ops/systemd/`: service templates.
- `ops/caddy/openlobbying.org.Caddyfile`: reverse proxy config.
- `ops/hetzner/`: Hetzner bootstrap notes and templates.

Production env must live on the server under `/etc/muckrake/app.env`.

- Shared required settings: `MUCKRAKE_DATABASE_URL`, `MUCKRAKE_PUBLISHED_DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`.
- Web runtime settings: `HOST`, `PORT`, `ORIGIN`, `NODE_ENV`.
- Optional shared settings: `MUCKRAKE_API_URL`, `MUCKRAKE_DATA_PATH`, `MUCKRAKE_ARTIFACT_PATH`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `NER_LLM_PROMPT_FILE`, `LOGFIRE_TOKEN`.
- `deploy_to_vps.sh` intentionally does not sync local `.env` files to the VPS.
- Release artifacts are stored under `MUCKRAKE_ARTIFACT_PATH` on the VPS. Back up that directory alongside Postgres.

For the full runbook, see `ops/hetzner/README.md`.
