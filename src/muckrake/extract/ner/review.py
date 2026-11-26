import json
import logging
import re
import sys
import textwrap
from typing import Any

import click
from rich.text import Text
from sqlalchemy.engine import Connection, RowMapping

from .editing import validate_extraction
from .storage import (
    auto_review,
    draw_sample,
    get_candidate,
    get_connection,
    init_db,
    list_candidates,
    list_sample_awaiting_review,
    review_candidate,
    sample_results,
    update_candidate_extraction,
)

log = logging.getLogger(__name__)

ACTION_TO_STATUS = {
    "x": "approved",
    "n": "rejected",
    "e": None,
    "u": None,
    "q": None,
}


def _collect_highlight_terms(entity: dict[str, Any]) -> list[str]:
    props = entity.get("properties", {})
    if not isinstance(props, dict):
        return []

    terms: list[str] = []
    for prop_name in ("name", "alias", "abbreviation"):
        for value in props.get(prop_name, []):
            if isinstance(value, str) and value.strip():
                terms.append(value.strip())
    return terms


def _entity_name(entity: dict[str, Any]) -> str:
    props = entity.get("properties", {})
    if not isinstance(props, dict):
        return "-"

    names = [v for v in props.get("name", []) if isinstance(v, str) and v.strip()]
    if names:
        return names[0]
    return "-"


def _highlight_terms(text: str, terms: list[str]) -> str:
    if not text or not terms:
        return text

    spans: list[tuple[int, int]] = []
    seen_terms: set[str] = set()
    for term in sorted(terms, key=len, reverse=True):
        normalized = term.strip().lower()
        if not normalized or normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            spans.append((match.start(), match.end()))

    if not spans:
        return text

    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue
        merged[-1][1] = max(merged[-1][1], end)

    chunks: list[str] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            chunks.append(text[cursor:start])
        chunks.append(click.style(text[start:end], fg="yellow", bold=True))
        cursor = end

    if cursor < len(text):
        chunks.append(text[cursor:])
    return "".join(chunks)


def _highlight_text(text: str, terms: list[str]) -> Text:
    rendered = Text(text)
    if not text or not terms:
        return rendered

    spans: list[tuple[int, int]] = []
    seen_terms: set[str] = set()
    for term in sorted(terms, key=len, reverse=True):
        normalized = term.strip().lower()
        if not normalized or normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            spans.append((match.start(), match.end()))

    if not spans:
        return rendered

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    for start, end in merged:
        rendered.stylize("bold yellow", start, end)
    return rendered


def _join_values(values: list[str], max_items: int = 3) -> str:
    cleaned = [v for v in values if isinstance(v, str) and v.strip()]
    if not cleaned:
        return "-"
    if len(cleaned) <= max_items:
        return " | ".join(cleaned)
    return " | ".join(cleaned[:max_items]) + f" (+{len(cleaned) - max_items})"


def _split_refs(values: list[str]) -> tuple[list[str], list[str]]:
    refs: list[str] = []
    plain: list[str] = []
    for value in values:
        if value.startswith("$ref:"):
            refs.append(value)
            continue
        plain.append(value)
    return refs, plain


def _parse_entities(row: RowMapping) -> list[dict[str, Any]]:
    entities = json.loads(row["extraction_json"])
    if not isinstance(entities, list):
        raise ValueError(f"Candidate {row['id']} has invalid extraction payload")
    return entities


def _edit_entities_in_editor(entities: list[Any]) -> list[dict[str, Any]] | None:
    initial = json.dumps(entities, indent=2, sort_keys=True) + "\n"
    edited = click.edit(initial, extension=".json")
    if edited is None:
        return None

    payload = json.loads(edited)
    validate_extraction(payload)
    return payload


def _style_label(label: str) -> str:
    return click.style(label, fg="bright_black", bold=True)


def _print_entity(entity: dict[str, Any], index: int) -> None:
    schema = entity.get("schema", "Unknown")
    key = entity.get("key")
    props = entity.get("properties", {})
    if not isinstance(props, dict):
        props = {}

    heading = click.style(f"#{index} {schema}", fg="green", bold=True)
    if key:
        heading = f"{heading}  {click.style(f'key={key}', fg='cyan')}"
    click.echo(f"  {heading}")

    names = [v for v in props.get("name", []) if isinstance(v, str)]
    aliases = [v for v in props.get("alias", []) if isinstance(v, str)]
    abbreviations = [v for v in props.get("abbreviation", []) if isinstance(v, str)]

    if names:
        click.echo(f"    {_style_label('name')} {_join_values(names)}")
    if aliases:
        click.echo(
            f"    {_style_label('alias')} {click.style(_join_values(aliases), fg='bright_cyan')}"
        )
    if abbreviations:
        click.echo(
            f"    {_style_label('abbr')} {click.style(_join_values(abbreviations), fg='magenta')}"
        )

    for prop_name in sorted(props):
        if prop_name in {"name", "alias", "abbreviation"}:
            continue
        values = [v for v in props.get(prop_name, []) if isinstance(v, str)]
        if not values:
            continue
        refs, plain = _split_refs(values)
        if refs:
            click.echo(
                f"    {_style_label(prop_name)} {click.style(_join_values(refs), fg='yellow')}"
            )
        if plain:
            click.echo(f"    {_style_label(prop_name)} {_join_values(plain)}")


def _print_candidate(row: RowMapping, index: int, total: int) -> None:
    entities = _parse_entities(row)
    terms: list[str] = []
    for entity in entities:
        if isinstance(entity, dict):
            terms.extend(_collect_highlight_terms(entity))

    click.echo("\n" + click.style("=" * 88, fg="bright_black"))
    click.echo(
        click.style(f"[{index}/{total}] Candidate #{row['id']}", fg="white", bold=True)
        + f"  {_style_label('dataset')} {row['dataset']}"
    )
    click.echo(
        f"{_style_label('source')} {row['entity_id']}"
        f"  {_style_label('field')} {row['property_name']}"
    )
    click.echo(_style_label("source text"))
    source_text = _highlight_terms(str(row["source_text"]), terms)
    for line in textwrap.wrap(source_text, width=88, break_long_words=False):
        click.echo(f"  {line}")

    click.echo(
        f"{_style_label('extracted entities')} "
        f"{click.style(str(len(entities)), fg='green', bold=True)}"
    )
    if not entities:
        click.echo("  - (none)")
        return

    for entity_idx, entity in enumerate(entities, start=1):
        if isinstance(entity, dict):
            _print_entity(entity, entity_idx)
        else:
            click.echo(f"  {entity_idx}. {entity}")


def _run_prompt_review(conn: Connection, rows: list[RowMapping]) -> dict[str, int]:
    approved = 0
    rejected = 0
    skipped = 0
    total = len(rows)

    idx = 0
    while idx < total:
        row = rows[idx]
        _print_candidate(row, idx + 1, total)
        action = click.prompt(
            "Action: [x] approve, [n] reject, [e] edit, [u] skip, [q] quit",
            type=click.Choice(sorted(ACTION_TO_STATUS), case_sensitive=False),
            default="x",
            show_choices=False,
        ).lower()

        if action == "q":
            break

        if action == "e":
            entities = _parse_entities(row)
            try:
                edited = _edit_entities_in_editor(entities)
            except Exception as exc:
                click.echo(click.style(f"Edit failed: {exc}", fg="red"))
                continue

            if edited is None:
                continue

            update_candidate_extraction(conn, row["id"], edited)
            refreshed = get_candidate(conn, row["id"])
            if refreshed is not None:
                rows[idx] = refreshed
            click.echo(click.style("Saved edited extraction.", fg="green"))
            continue

        status = ACTION_TO_STATUS[action]
        if status == "approved":
            review_candidate(conn, row["id"], status=status)
            approved += 1
        elif status == "rejected":
            review_candidate(conn, row["id"], status=status)
            rejected += 1
        else:
            skipped += 1
        idx += 1

    return {
        "approved": approved,
        "rejected": rejected,
        "skipped": skipped,
        "remaining": max(0, total - (approved + rejected + skipped)),
    }


def _run_tui_review(
    conn: Connection, rows: list[RowMapping], pool: str | None, dataset_name: str | None
) -> dict[str, int]:
    from .review_app import run_review_app

    return run_review_app(conn, rows, pool=pool, dataset_name=dataset_name)


def run_ner_review(
    dataset_name: str | None = None,
    limit: int | None = None,
    sample: int | None = None,
    pool: str = "approved",
) -> None:
    """Review pending candidates, or, with ``sample``, a sample of automatic decisions.

    ``sample`` is the size of the sample for ``pool`` (``approved`` or ``rejected``
    by ``muckrake/auto``): only enough candidates to reach it are drawn, then every
    candidate sampled from that pool that no person has decided yet is reviewed.
    Running the same command again resumes the sample.
    """
    conn = get_connection()
    init_db(conn)
    if sample is None:
        rows = list_candidates(conn, dataset_name=dataset_name, status="pending", limit=limit)
        empty = "No pending NER candidates to review."
    else:
        drawn = draw_sample(conn, sample, pool=pool, dataset_name=dataset_name)
        rows = list_sample_awaiting_review(conn, pool=pool, dataset_name=dataset_name)
        click.echo(
            f"Auto-{pool} sample of {sample}: drew {drawn} new candidates; "
            f"{len(rows)} sampled candidates to review."
        )
        empty = f"No sampled auto-{pool} NER candidates to review."

    if not rows:
        click.echo(empty)
        conn.close()
        return

    if sys.stdout.isatty() and sys.stdin.isatty():
        summary = _run_tui_review(conn, rows, pool if sample is not None else None, dataset_name)
    else:
        summary = _run_prompt_review(conn, rows)

    conn.close()
    click.echo(
        "\nReview complete. "
        f"approved={summary['approved']} "
        f"rejected={summary['rejected']} "
        f"skipped={summary['skipped']} "
        f"remaining={summary['remaining']}"
    )
    if sample is not None:
        conn = get_connection()
        counts = sample_results(conn, dataset_name=dataset_name)[pool]
        conn.close()
        click.echo(
            f"Auto-{pool} sample so far: sampled={counts['sampled']} "
            f"decided={counts['decided']} approved_unedited={counts['approved_unedited']} "
            f"approved_edited={counts['approved_edited']}"
        )
        entities = counts["entities"]
        click.echo(
            f"Entities: checked={entities['checked']} kept={entities['kept']} "
            f"removed={entities['removed']} added={entities['added']}"
            f" (edited without an original: {counts['edited_without_original']})"
        )
        for reviewer, by in sorted(counts["by_reviewer"].items()):
            e = by["entities"]
            click.echo(
                f"  {reviewer}: decided={by['decided']} "
                f"approved_unedited={by['approved_unedited']} "
                f"approved_edited={by['approved_edited']}; entities checked={e['checked']} "
                f"kept={e['kept']} removed={e['removed']} added={e['added']}"
            )


def run_ner_auto_review(dataset_name: str | None = None) -> None:
    conn = get_connection()
    init_db(conn)
    approved, rejected = auto_review(conn, dataset_name=dataset_name)
    conn.close()
    click.echo(f"Auto review complete. approved={approved} rejected={rejected}")
