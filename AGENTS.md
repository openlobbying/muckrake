# Instructions for AI agents

Muckrake crawls various [datasets](/datasets/), creates [FollowTheMoney](https://followthemoney.tech/) entities and relationships, servese them via a [FastAPI backend](/src/muckrake/api/server.py) and a [SvelteKit frontend](/openlobbying/). It is used for OpenLobbying.org, a public website for exploring UK lobbying data (donations, meetings, lobbying representation, etc.).

## FollowTheMoney

Always prefer using existing FollowTheMoney functions and schemata throughout the codebase. We also heavily rely on the [`nomenklatura`](https://github.com/opensanctions/nomenklatura) library for entity resolution, as well as data storage. Check the documentation and codebase to see if you can use existing functions before writing new ones, chances are they exist.

Key Resources:
- FtM entity schemata: https://followthemoney.tech/explorer/schemata/
- FtM property types: https://followthemoney.tech/explorer/types/

Crawlers must crash loudly on uncertain data, never emit ambiguous information.

## Python conventions

- `MUCKRAKE_DATABASE_URL` must point to Postgres in all environments.
- Production publishing uses one curated DB artifact (must include resolver + ner_candidates state).
- Frontend calls backend through relative `/api/*` routes (no hardcoded localhost URLs).
- For local frontend dev, Vite proxies `/api` to `http://127.0.0.1:8000`.
- Deployment templates and VPS runbook live in `docs/deploy/`.
- Do not commit secrets or server-specific private values into repo files.
Always use `uv` to run Python commands, never `python`, `python3` or `pip` directly.

## Good practices

Keep code simple and tidy. We don't need excessive abstractions and over-engineering. We don't need backwards compatibility. We don't need to account for edge cases before they arise.

Keep documentation (README.md and AGENTS.md files) up to date and accurate when you add new features or make changes.

You have access to the `gh` CLI tool, use it to interact with GitHub. However, don't commit, push or create pull requests directly unless directed to do so.
