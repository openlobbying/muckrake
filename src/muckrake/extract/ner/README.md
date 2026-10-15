# Entity Extraction

This package splits text fields that name several entities into separate FtM
entity candidates, for review before they are applied. Extraction strategies
share one interface; there are two:

- `delimiter` (deterministic splitter, no API key needed)
- `llm` (an OpenRouter or Anthropic model via PydanticAI)

## Components

- CLI commands: `muckrake ner-extract`, `ner-review`, `ner-export`, `ner-import`
- Strategy registry under `src/muckrake/extract/ner/engines/`
- Implemented strategies: `delimiter`, `llm`
- Candidate persistence in the working database (`MUCKRAKE_DATABASE_URL`), table `ner_candidates`

Code locations:

- pipeline: `src/muckrake/extract/ner/pipeline.py`
- engines registry: `src/muckrake/extract/ner/engines/__init__.py`
- delimiter engine: `src/muckrake/extract/ner/engines/delimited.py`
- LLM engine and prompt: `src/muckrake/extract/ner/engines/llm.py`, `llm_prompt.py`
- load-time application: `src/muckrake/extract/ner/materialize.py`
- review TUI: `src/muckrake/extract/ner/review.py`
- storage: `src/muckrake/extract/ner/storage.py`

## Input model

Extraction runs over normalized crawler output (`statements.pack.csv`), not raw source files.

Currently selected statement fields:

- `LegalEntity.name`
- `Organization.name`
- `Company.name`
- `Person.name`

This keeps the process format-agnostic across CSV/JSON/HTML-backed datasets.

Only texts of 20+ characters containing a separator (`,`, `;` or `:`) are
extracted. "and", "&" and brackets are nearly always part of one name
("Department for Work & Pensions"), so they don't trigger extraction on their own.

## Current strategy: `delimiter`

- Splits candidate text on commas and semicolons.
- Emits a list of FtM-aligned entity fragments.

Each extracted entity is stored as an FtM-style JSON fragment without `id`:

```json
{
  "schema": "LegalEntity",
  "properties": {
    "name": ["Example Name"]
  }
}
```

Using `LegalEntity` is deliberate, because delimiter splitting alone
cannot reliably distinguish `Person` vs `Organization`.

## LLM strategy: `llm`

- Uses `pydantic-ai`. `LLM_MODEL` picks the provider and model (from environment, with `.env` fallback):
  - OpenRouter: `openrouter:<model>`, with `OPENROUTER_API_KEY`.
  - Anthropic: `anthropic:<model>`, with `ANTHROPIC_API_KEY`.
  - The provider prefix is required. Without it the extractor fails to start, with
    `Unknown provider: ...` (for a name containing `/`) or `Unknown model: ...`.
  - With the current lockfile, `openrouter:` models fail to start with "Please
    install `openai`": the locked `openai` package is older than the locked
    `pydantic-ai-slim` requires.
- Produces FtM-style fragments in the same `entities` format as delimiter.
- Supports relation links via local keys and `$ref:<key>` values in extracted properties
  (for example `Employment.employee -> "$ref:p1"`).
- Validates output against FollowTheMoney schemata/properties and retries the model on errors.
- Traces each model call with Logfire: the engine calls
  `configure_logging(enable_logfire=True)`, and setting `LOGFIRE_TOKEN` sends the
  traces to Logfire.

Prompt configuration:

- Default prompt is in `src/muckrake/extract/ner/engines/llm_prompt.py`.
- You can override prompt text with `NER_LLM_PROMPT_FILE=/path/to/prompt.txt`.

## Storage

Candidates are stored in the working database (SQLite `data/muckrake.db` by default, or `MUCKRAKE_DATABASE_URL`), table `ner_candidates`.

Main columns:

- `dataset`, `entity_id`, `schema`, `property_name`
- `source_text`, `fingerprint`
- `extractor`
- `status` (`pending`, `approved`, `rejected`)
- `reviewer`, `reviewed_at`
- `extraction_json`, `created_at`, `updated_at`

`extractor_version` still exists internally in the table for compatibility,
but it is fixed by the app and not exposed in CLI.

Uniqueness key:

- `(dataset, entity_id, property_name, fingerprint, extractor, extractor_version)`

So reruns with unchanged input + extractor configuration are idempotent.

## Load-time import

`muckrake load`, `muckrake xref` and `muckrake release-build` read `ner_candidates` and apply matching extractions before materializing statements:

- if a candidate matches `(property_name, fingerprint)`, in any dataset, the original source entity is skipped,
- extracted fragments from `extraction_json` are materialized as new FtM entities,
- references to the original entity ID are rewritten to the extracted entity IDs,
- generated IDs use source dataset prefix + extracted `name` (for example `<prefix>-...`),
- if there is no matching candidate, loading behaves exactly as before.

Only candidates with `status = approved` are applied.

As with dedupe decisions, the source statements are left unchanged; approved
candidates change what is materialized from them. When several approved
candidates match, the latest is applied.

## Usage

Run for one dataset:

```bash
uv run muckrake ner-extract <dataset>
```

Choose extractor:

```bash
uv run muckrake ner-extract <dataset> --extractor delimiter --limit 20

# basic LLM extraction
uv run muckrake ner-extract <dataset> --extractor llm --limit 20
```

Extract a single source entity:

```bash
uv run muckrake ner-extract <dataset> --entity-id <entity-id> --extractor llm
```

Run across all datasets:

```bash
uv run muckrake ner-extract
```

Each distinct text is extracted once: a text already extracted for any dataset
is skipped, because approved candidates apply wherever that text appears. Use
`--workers N` to extract N texts in parallel (useful with an LLM).

Review pending candidates:

```bash
# One dataset
uv run muckrake ner-review <dataset>

# All datasets
uv run muckrake ner-review

# Decide every pending candidate without review
uv run muckrake ner-review --auto
```

Save and restore candidates (with review decisions) outside the database, so
paid LLM extractions are never repeated:

```bash
uv run muckrake ner-export ner/candidates.jsonl.gz
uv run muckrake ner-import ner/candidates.jsonl.gz
```

Import adds only candidates that aren't already present, so local review
decisions are kept.

`--auto` approves every pending split and rejects extractions that only repeat
the source text (so the original entity and its ID are kept). It records the
reviewer as `muckrake/auto` and only touches pending candidates, so decisions
made in the review TUI are never overwritten.

Review controls:

- `x` approve candidate
- `n` reject candidate
- `e` edit extracted JSON in your `$EDITOR`
- `u` skip candidate
- `q` quit review

When you press `e`, Muckrake opens a temporary JSON file in your terminal editor.
How to exit depends on the editor:

- Vim/Vi: press `Esc`, type `:wq`, press `Enter` (save + exit)
- Vim/Vi without saving: `Esc`, `:q!`, `Enter`
- Nano: `Ctrl+X`, then `Y` + `Enter` to save (or `N` to discard)

Tip: set an editor you are comfortable with before review:

```bash
export EDITOR=nano
# or
export EDITOR=vim
```

## Quick test

1. Crawl a dataset so statements exist:

```bash
uv run muckrake crawl <dataset>
```

2. Run extraction (the `delimiter` extractor needs no API key; the default,
   `llm`, needs `LLM_MODEL` and its API key):

```bash
uv run muckrake ner-extract <dataset> --extractor delimiter --limit 20
```

3. Review and approve a few candidates:

```bash
uv run muckrake ner-review <dataset> --limit 20
```

4. Load dataset and verify approved candidates are applied:

```bash
uv run muckrake load <dataset>
```

5. Run extraction again with same options and confirm no new rows are inserted.

6. Check row count:

```bash
uv run python -c "import muckrake; from sqlalchemy import create_engine, text; from muckrake.settings import SQL_URI; e=create_engine(SQL_URI); print(e.connect().execute(text('select count(*) from ner_candidates')).scalar())"
```
