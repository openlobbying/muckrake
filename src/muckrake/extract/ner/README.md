# Entity Extraction (Prototype)

This package contains a minimal, extensible named-entity extraction pipeline.

The goal is to support multiple extraction strategies behind one interface.
Implemented now:

- `delimiter` (deterministic splitter)
- `llm` (basic OpenRouter-powered extractor via PydanticAI)

## What exists now

- CLI command: `muckrake ner-extract`
- Strategy registry under `src/muckrake/extract/ner/engines/`
- Implemented strategies: `delimiter`, `llm`
- Candidate persistence into `data/muckrake.db` table: `ner_candidates`

Code locations:

- pipeline: `src/muckrake/extract/ner/pipeline.py`
- engines registry: `src/muckrake/extract/ner/engines/__init__.py`
- delimiter engine: `src/muckrake/extract/ner/engines/delimited.py`
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

Using `LegalEntity` is deliberate at this stage because delimiter splitting alone
cannot reliably distinguish `Person` vs `Organization`.

## LLM strategy: `llm` (basic)

- Uses `pydantic-ai`. `LLM_MODEL` picks the provider and model (from environment, with `.env` fallback):
  - OpenRouter: `openrouter:stepfun/step-3.5-flash:free` (or just `stepfun/step-3.5-flash:free`), with `OPENROUTER_API_KEY`.
  - Anthropic: `anthropic:claude-haiku-5-5`, with `ANTHROPIC_API_KEY`.
- Produces FtM-style fragments in the same `entities` format as delimiter.
- Supports relation links via local keys and `$ref:<key>` values in extracted properties
  (for example `Employment.employee -> "$ref:p1"`).
- Validates output against FollowTheMoney schemata/properties and retries the model on errors.
- Centralized Logfire tracing (`configure_logging(app=...)`).
  Set `LOGFIRE_TOKEN` to send traces to Logfire.

Prompt configuration:

- Default prompt is in `src/muckrake/extract/ner/engines/llm_prompt.py`.
- You can override prompt text with `NER_LLM_PROMPT_FILE=/path/to/prompt.txt`.

## Storage

Candidates are stored in `data/muckrake.db`, table `ner_candidates`.

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

`muckrake load` and `muckrake xref` both read `ner_candidates` and apply matching extractions before materializing statements:

- if a candidate matches `(property_name, fingerprint)`, in any dataset, the original source entity is skipped,
- extracted fragments from `extraction_json` are materialized as new FtM entities,
- references to the original entity ID are rewritten to the extracted entity IDs,
- generated IDs use source dataset prefix + extracted `name` (for example `gb-meet-...`),
- if there is no matching candidate, loading behaves exactly as before.

Only candidates with `status = approved` are applied.

This mirrors the dedupe philosophy: extraction decisions alter load-time materialization.
Current implementation applies the latest approved matching candidate.

## Usage

Run for one dataset:

```bash
uv run muckrake ner-extract open_access
```

Choose extractor:

```bash
uv run muckrake ner-extract open_access --extractor delimiter --limit 20

# basic LLM extraction
uv run muckrake ner-extract open_access --extractor llm --limit 20
```

Extract a single source entity:

```bash
uv run muckrake ner-extract open_access --entity-id gb-meetings-12345 --extractor llm
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
uv run muckrake ner-review open_access

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
uv run muckrake crawl open_access
```

2. Run extraction:

```bash
uv run muckrake ner-extract open_access --limit 20
```

3. Review and approve a few candidates:

```bash
uv run muckrake ner-review open_access --limit 20
```

4. Load dataset and verify approved candidates are applied:

```bash
uv run muckrake load open_access
```

5. Run extraction again with same options and confirm no new rows are inserted.

6. Check row count:

```bash
uv run python -c "from sqlalchemy import create_engine, text; from muckrake.settings import SQL_URI; e=create_engine(SQL_URI); print(e.connect().execute(text('select count(*) from ner_candidates')).scalar())"
```

## Next planned pieces

- Add additional extraction engines to `ner/engines/`.
- Load only approved candidates into FtM entities.
