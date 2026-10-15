# Instructions for AI agents

Muckrake is the reusable FollowTheMoney data pipeline core. It provides dataset discovery, crawl execution, loading, release-building, dedupe, and NER support for application repos such as OpenLobbying.

muckrake must stay project-agnostic: crawlers, apps and schema extensions for a particular project live in that project's repository (for OpenLobbying, the sibling `../openlobbying/`). `scripts/litmus.sh` checks this in CI. The only dataset here is the quickstart example in `examples/hello_dataset/`.

## FollowTheMoney

Always prefer using existing FollowTheMoney functions and schemata throughout the codebase. We also heavily rely on the [`nomenklatura`](https://github.com/opensanctions/nomenklatura) library for entity resolution, as well as data storage. Check the documentation and codebase to see if you can use existing functions before writing new ones, chances are they exist.

Project-specific FollowTheMoney schema extensions should live in the consuming application repo, not in `muckrake` itself. `muckrake` discovers extension directories from `MUCKRAKE_FTM_SCHEMA_PATHS` and `./ftm_schema_ext/` in the current working directory.

Key Resources:
- FtM entity schemata: https://followthemoney.tech/explorer/schemata/
- FtM property types: https://followthemoney.tech/explorer/types/

Crawlers must crash loudly on uncertain data, never emit ambiguous information. In a crawler that wraps its work in `dataset.run_unit(...)`, that crash fails only the current unit: nothing from it is emitted, the run finishes `partial`, and `muckrake crawl <name> --retry-failed` re-runs it (see README "Units of work"). A known gap that isn't an error (a pagination cap, a missing linked file) must be recorded with `dataset.warn_incomplete(reason, **context)`, never only logged, so the run is marked `partial`.

## Python conventions

Always use `uv` to run Python commands, never `python`, `python3` or `pip` directly.

## Good practices

Keep code simple and tidy. We don't need excessive abstractions and over-engineering. We don't need backwards compatibility. We don't need to account for edge cases before they arise.

When working with crawlers, remember that `muckrake` discovers dataset configs from `./datasets/` in the current working directory and from `MUCKRAKE_DATASET_PATHS` when explicitly set.

Keep documentation (README.md and AGENTS.md files) up to date and accurate when you add new features or make changes. `docs/cli.md` and `docs/env.md` are generated: after changing a command, option or environment variable (`ENV_VARS` in `src/muckrake/settings.py`), run `uv run python scripts/gen_docs.py`. Leave comments in the code for future developers to understand your thought process.

You have access to the `gh` CLI tool, use it to interact with GitHub. However, don't commit, push or create pull requests directly unless directed to do so.
