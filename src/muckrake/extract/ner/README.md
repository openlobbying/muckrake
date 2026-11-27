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
- `sampled_at` and `sampled_status`, set when the candidate is drawn into a review
  sample: when, and the automatic status it had then (its pool)
- `edited_at`, set whenever a reviewer saves an edited extraction with `e`, and
  `original_extraction_json`, the extraction as it was before the first edit
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

### Measuring precision

`--auto` decides candidates nobody has checked. To measure how good those
decisions are, review a random sample of them by hand. There are two pools:

```bash
uv run muckrake ner-review --sample 100             # auto-approved splits
uv run muckrake ner-review --sample 100 --rejected  # names auto-rejected as whole
uv run muckrake ner-review <dataset> --sample 100   # one dataset
```

`--sample N` is the size of the pool's sample. It draws only enough random
candidates to bring the pool's sample up to N, from those `muckrake/auto`
decided and never sampled before, sets their `sampled_at` and `sampled_status`,
and opens the review on every candidate sampled from that pool that no person
has decided yet. Running the same command again draws nothing new and resumes
the candidates you skipped or left when you quit; a bigger N tops the sample
up. With a dataset, N counts that dataset's sample only. `--rejected` needs
`--sample`, and `--sample` can't be combined with `--auto` or `--limit`.

After a sample review, the command prints the pool's counts, per split and per
entity. `sample_results` in `muckrake.extract.ner.storage` returns them for both
pools. An edit counts only if it was saved after the candidate was sampled.

Per split, each candidate is one unit: sampled, decided by a person, approved as
it was (`approved_unedited`), and edited then approved (`approved_edited`). This
answers how often an automatic decision was right as a whole.

- Approved pool: approved_unedited / decided is the precision of the automatic
  splits. approved_edited counts the splits you had to correct, which are errors
  too. Approve a split that is right as it is, fix one that is nearly right with
  `e` and approve it, and reject one that is wrong.
- Rejected pool: approved_edited / decided is how often a name left whole was
  really composite. Split such a name with `e`, then approve it. Reject a name
  that is one entity, so the original entity is kept.

#### Judging a split

A split is right only if it has every entity the text names, no entity the text
doesn't name, and the links between them. These are errors, so fix the split and
approve it:

- An entity the text names is missing.
- An entity is made up: a role, title, description or event recorded as a person
  or organisation, such as "Chief Constable", "former Prime Minister of …" or
  "Breakfast Roundtable".
- Two entities are merged into one, or one is split into two. That includes an
  organisation recorded as another's alias.
- An entity has the wrong kind of schema, such as a company recorded as a Person.
- An abbreviation is expanded wrongly, or a generic term such as "ICB" is
  recorded as one body's abbreviation.
- A person is named with their organisation but not linked to it. When the text
  pairs a person with an organisation, with or without a role, the split must
  link them, for example with an `Employment`.

These aren't errors, so approve the split as it is:

- Spelling and typos copied from the source. Keep the source's spelling; linking
  variants of a name is deduplication's job.
- A close choice between organisation schemas, such as `Organization`, `Company`
  or `PublicBody`.
- An abbreviation expanded correctly.
- A title kept in a name, such as "Dr" or "MP".

Per entity, under `entities`, each extracted entity is one unit, relative to what
the automatic decision produced: `checked`, `kept` unchanged, and `removed` and
`added` by you. This answers how much of the extracted data was right, since a
split with one wrong entity out of three is mostly right.

- An unedited approval keeps every entity.
- An edited approval is compared with the extraction before its first edit
  (`original_extraction_json`). Entities match on schema and properties, ignoring
  `key` and order; a `$ref` value is compared as the schema and first name of the
  entity it points to, so renaming a body also changes the relationship to it.
- Rejecting an auto-approved split removes all its entities. Rejecting an
  auto-rejected name keeps its single entity.
- Candidates edited before originals were kept have no original to compare with.
  They count per split only, and in `edited_without_original`.

In the approved pool, kept / checked is the entity-level precision. In the
rejected pool, added counts the entities the automatic decision missed.

Decisions by different reviewers are reported separately, as well as in the
totals: `sample_results` gives each pool a `by_reviewer` breakdown keyed by the
`reviewer` name, with the same per-split and per-entity counts, and the command
prints a line per reviewer. A model checking a model's output isn't an
independent check, so a sample reviewed partly by a person and partly by a model
should be read reviewer by reviewer. Record each reviewer under their own name.

`ner-review` records the reviewer it's given with `--reviewer` (or
`MUCKRAKE_REVIEWER`), and otherwise your login name; it refuses `root`, as in a
container, so name yourself there. Reviewer names say what kind of decision it
was, and `review_kind` in `muckrake.extract.ner.storage` reads them:

| Kind | Reviewer | Example |
|---|---|---|
| automatic | `muckrake/auto`, set by `--auto` | `muckrake/auto` |
| model | `model:<name>`, for a model reviewing the extractions | `model:claude` |
| human | anything else: the person's own name | `jane` |

`sample_results` also gives each pool a `by_kind` breakdown with the same counts.

`ner-export` and `ner-import` carry `sampled_at`, `sampled_status`, `edited_at`
and `original_extraction_json`, so a sample and its edits are kept with the
decisions.

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
