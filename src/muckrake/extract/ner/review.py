import json
import logging
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

import click
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from sqlalchemy.engine import Connection, RowMapping
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Static

from .storage import (
    get_candidate,
    get_connection,
    init_db,
    list_candidates,
    review_candidate,
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


@dataclass
class ReviewEvent:
    candidate_id: int
    action: str
    schema: str
    when: str


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


def _validate_entities_payload(payload: Any) -> None:
    if not isinstance(payload, list):
        raise ValueError("Extraction must be a JSON array")

    for index, entity in enumerate(payload, start=1):
        if not isinstance(entity, dict):
            raise ValueError(f"Entity #{index} must be an object")

        schema = entity.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError(f"Entity #{index} is missing a string 'schema'")

        props = entity.get("properties")
        if not isinstance(props, dict):
            raise ValueError(f"Entity #{index} is missing an object 'properties'")

        for prop_name, values in props.items():
            if not isinstance(prop_name, str):
                raise ValueError(f"Entity #{index} has non-string property name")
            if not isinstance(values, list):
                raise ValueError(
                    f"Entity #{index} property '{prop_name}' must be an array"
                )
            for value in values:
                if not isinstance(value, str):
                    raise ValueError(
                        f"Entity #{index} property '{prop_name}' values must be strings"
                    )


def _edit_entities_in_editor(entities: list[Any]) -> list[dict[str, Any]] | None:
    initial = json.dumps(entities, indent=2, sort_keys=True) + "\n"
    edited = click.edit(initial, extension=".json")
    if edited is None:
        return None

    payload = json.loads(edited)
    _validate_entities_payload(payload)
    return payload


def _render_candidate(row: RowMapping, index: int, total: int) -> RenderableType:
    entities = _parse_entities(row)
    terms: list[str] = []
    for entity in entities:
        if isinstance(entity, dict):
            terms.extend(_collect_highlight_terms(entity))

    header = Text.assemble(
        (f"Candidate #{row['id']}", "bold white"),
        (f"   [{index}/{total}]", "bright_black"),
    )

    meta = Table.grid(expand=True)
    meta.add_column(style="bright_black", width=12)
    meta.add_column(style="white")
    meta.add_row("dataset", str(row["dataset"]))
    meta.add_row("entity", str(row["entity_id"]))
    meta.add_row("field", str(row["property_name"]))

    source = _highlight_text(str(row["source_text"]), terms)

    entities_table = Table(expand=True, box=None)
    entities_table.add_column("#", style="bright_black", width=3)
    entities_table.add_column("Schema", style="green", width=14)
    entities_table.add_column("Name", style="bold")
    entities_table.add_column("Alias", style="cyan")
    entities_table.add_column("Abbr", style="magenta", width=14)
    entities_table.add_column("Refs", style="yellow", width=14)
    entities_table.add_column("Other", style="white")

    if not entities:
        entities_table.add_row("-", "-", "(none)", "-", "-", "-", "-")
    else:
        for entity_idx, entity in enumerate(entities, start=1):
            if not isinstance(entity, dict):
                entities_table.add_row(
                    str(entity_idx), "invalid", "-", "-", "-", "-", str(entity)
                )
                continue

            props = entity.get("properties", {})
            if not isinstance(props, dict):
                props = {}

            aliases = [v for v in props.get("alias", []) if isinstance(v, str)]
            abbreviations = [
                v for v in props.get("abbreviation", []) if isinstance(v, str)
            ]

            refs: list[str] = []
            other_parts: list[str] = []
            for prop_name in sorted(props.keys()):
                if prop_name in {"name", "alias", "abbreviation"}:
                    continue
                values = [v for v in props.get(prop_name, []) if isinstance(v, str)]
                if not values:
                    continue
                prop_refs, prop_plain = _split_refs(values)
                refs.extend(prop_refs)
                if prop_plain:
                    other_parts.append(
                        f"{prop_name}={_join_values(prop_plain, max_items=2)}"
                    )

            entities_table.add_row(
                str(entity_idx),
                str(entity.get("schema", "Unknown")),
                _entity_name(entity),
                _join_values(aliases),
                _join_values(abbreviations),
                _join_values(refs),
                _join_values(other_parts, max_items=3),
            )

    return Group(
        header,
        "",
        meta,
        "",
        Text("Source text", style="bold bright_black"),
        source,
        "",
        Text(f"Extracted entities ({len(entities)})", style="bold bright_black"),
        entities_table,
    )


class NERReviewState:
    def __init__(self, conn: Connection, rows: list[RowMapping]):
        self.conn = conn
        self.rows = rows
        self.index = 0
        self.approved = 0
        self.rejected = 0
        self.skipped = 0
        self.events: list[ReviewEvent] = []

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def current(self) -> Optional[RowMapping]:
        if self.index >= self.total:
            return None
        return self.rows[self.index]

    @property
    def done(self) -> bool:
        return self.current is None

    def decide(self, action: str) -> None:
        row = self.current
        if row is None:
            return

        status = ACTION_TO_STATUS.get(action)
        if status == "approved":
            review_candidate(self.conn, row["id"], status=status)
            self.approved += 1
        elif status == "rejected":
            review_candidate(self.conn, row["id"], status=status)
            self.rejected += 1
        else:
            self.skipped += 1

        self.events.append(
            ReviewEvent(
                candidate_id=row["id"],
                action=action,
                schema=str(row["schema"]),
                when=datetime.now(UTC).strftime("%H:%M:%S"),
            )
        )
        self.index += 1

    def summary(self) -> dict[str, int]:
        return {
            "approved": self.approved,
            "rejected": self.rejected,
            "skipped": self.skipped,
            "remaining": max(0, self.total - self.index),
        }

    def edit_current(self, extraction: list[dict[str, Any]]) -> None:
        row = self.current
        if row is None:
            return

        update_candidate_extraction(self.conn, row["id"], extraction)
        refreshed = get_candidate(self.conn, row["id"])
        if refreshed is not None:
            self.rows[self.index] = refreshed

        self.events.append(
            ReviewEvent(
                candidate_id=row["id"],
                action="e",
                schema=str(row["schema"]),
                when=datetime.now(UTC).strftime("%H:%M:%S"),
            )
        )


class ReviewWidget(Static):
    def on_mount(self) -> None:
        self.reload()

    def reload(self) -> None:
        app = self.app
        assert isinstance(app, NERReviewApp)
        if app.state.done:
            self.update(Text("No pending candidates.", justify="center"))
            return
        row = app.state.current
        assert row is not None
        self.update(_render_candidate(row, app.state.index + 1, app.state.total))


class HistoryWidget(Static):
    is_visible = False

    def on_mount(self) -> None:
        self.border_title = "History"
        self._apply_visibility()
        self.reload()

    def toggle_visible(self) -> None:
        self.is_visible = not self.is_visible
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        self.styles.display = "block" if self.is_visible else "none"

    def reload(self) -> None:
        app = self.app
        assert isinstance(app, NERReviewApp)

        table = Table(expand=True, box=None)
        table.add_column("When", style="bright_black", width=9)
        table.add_column("ID", style="white", width=7)
        table.add_column("Action", width=8)
        table.add_column("Schema", style="bright_black")

        action_style = {"x": "green", "n": "red", "u": "yellow", "e": "cyan"}
        action_label = {"x": "approve", "n": "reject", "u": "skip", "e": "edit"}

        for event in app.state.events[-25:]:
            table.add_row(
                event.when,
                str(event.candidate_id),
                Text(
                    action_label.get(event.action, event.action),
                    style=action_style.get(event.action, "white"),
                ),
                event.schema,
            )

        if not app.state.events:
            table.add_row("-", "-", "-", "No actions yet")
        self.update(table)


class NERReviewApp(App[dict[str, int]]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        layout: horizontal;
        height: 1fr;
    }

    VerticalScroll {
        width: 1fr;
        border: solid white;
        padding: 1;
    }

    ReviewWidget {
        width: 1fr;
        height: auto;
    }

    HistoryWidget {
        width: 52;
        border: solid white;
        padding: 1;
    }
    """

    BINDINGS = [
        ("x", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("e", "edit", "Edit JSON"),
        ("u", "skip", "Skip"),
        ("h", "history", "Toggle History"),
        ("q", "quit_review", "Quit"),
    ]

    def __init__(self, state: NERReviewState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        self.title = "NER Review"
        yield Horizontal(
            VerticalScroll(ReviewWidget(), id="review"),
            HistoryWidget(),
            id="main",
        )
        yield Footer()

    def _refresh(self) -> None:
        review = self.query_one(ReviewWidget)
        review.reload()
        self.query_one("#review", VerticalScroll).scroll_home(animate=False)
        history = self.query_one(HistoryWidget)
        history.reload()
        history.refresh(layout=True)

    def _advance(self, action: str) -> None:
        self.state.decide(action)
        if self.state.done:
            self.exit(self.state.summary())
            return
        self._refresh()

    async def action_approve(self) -> None:
        self._advance("x")

    async def action_reject(self) -> None:
        self._advance("n")

    async def action_skip(self) -> None:
        self._advance("u")

    async def action_edit(self) -> None:
        row = self.state.current
        if row is None:
            return

        with self.suspend():
            try:
                entities = _parse_entities(row)
                edited = _edit_entities_in_editor(entities)
            except Exception as exc:
                click.echo(click.style(f"Edit failed: {exc}", fg="red"))
                return

        if edited is None:
            return
        self.state.edit_current(edited)
        self._refresh()

    async def action_history(self) -> None:
        history = self.query_one(HistoryWidget)
        history.toggle_visible()
        self._refresh()

    async def action_quit_review(self) -> None:
        self.exit(self.state.summary())


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
        f"{_style_label('extracted entities')} {click.style(str(len(entities)), fg='green', bold=True)}"
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


def _run_tui_review(conn: Connection, rows: list[RowMapping]) -> dict[str, int]:
    state = NERReviewState(conn, rows)
    app = NERReviewApp(state)
    result = app.run()
    if result is None:
        return state.summary()
    return result


def run_ner_review(
    dataset_name: Optional[str] = None, limit: Optional[int] = None
) -> None:
    conn = get_connection()
    init_db(conn)
    rows = list_candidates(
        conn, dataset_name=dataset_name, status="pending", limit=limit
    )

    if not rows:
        click.echo("No pending NER candidates to review.")
        conn.close()
        return

    if sys.stdout.isatty() and sys.stdin.isatty():
        summary = _run_tui_review(conn, rows)
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
