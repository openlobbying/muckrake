"""The ``ner-review`` screen: review candidates one by one, edit their extraction in
place, and approve or reject them.

Edits are staged on the current candidate. ``ctrl+s`` saves them, and approving
saves them first, so an edit followed by an approval is an edited approval. Every
save goes through ``update_candidate_extraction``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text
from sqlalchemy.engine import Connection, RowMapping
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Label, Select, Static, TextArea

from .editing import (
    BODY_SCHEMAS,
    EXTRACTION_SCHEMAS,
    Extraction,
    add_entity,
    delete_entity,
    describe_ref,
    entity_name,
    form_fields,
    is_ref_property,
    replace_entity,
    split_entity,
    validate_extraction,
    with_keys,
)
from .storage import (
    get_candidate,
    restore_review,
    review_candidate,
    sample_results,
    update_candidate_extraction,
)

DIALOG_HINT = "Tab / Shift+Tab: next / previous field · Ctrl+S: save · Esc: cancel"
# Strip these from both sides of a split at the cursor.
SPLIT_TRIM = " \t,-–:;"

ACTION_LABELS = {
    "x": ("approve", "green"),
    "n": ("reject", "red"),
    "u": ("skip", "yellow"),
    "e": ("edit", "cyan"),
    "z": ("undo", "magenta"),
}


@dataclass
class ReviewEvent:
    candidate_id: int
    action: str
    schema: str
    when: str


@dataclass
class Decision:
    """One approve, reject or skip, with what it replaced, so it can be undone."""

    index: int
    candidate_id: int
    action: str
    status: str
    reviewer: str | None
    reviewed_at: str | None


class ReviewSession:
    """The queue of candidates being reviewed, and what this session has done to them."""

    def __init__(
        self,
        conn: Connection,
        rows: list[RowMapping],
        pool: str | None = None,
        dataset_name: str | None = None,
    ):
        self.conn = conn
        self.rows = rows
        self.pool = pool
        self.dataset_name = dataset_name
        self.index = 0
        self.staged: Extraction | None = None
        self.decisions: list[Decision] = []
        self.events: list[ReviewEvent] = []

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def current(self) -> RowMapping | None:
        return self.rows[self.index] if self.index < self.total else None

    @property
    def extraction(self) -> Extraction:
        """The current candidate's extraction, with any staged edits."""
        if self.staged is not None:
            return self.staged
        row = self.current
        return json.loads(row["extraction_json"]) if row is not None else []

    def count(self, action: str) -> int:
        return sum(1 for decision in self.decisions if decision.action == action)

    def summary(self) -> dict[str, int]:
        return {
            "approved": self.count("x"),
            "rejected": self.count("n"),
            "skipped": self.count("u"),
            "remaining": max(0, self.total - self.index),
        }

    def _log(self, row: RowMapping, action: str) -> None:
        self.events.append(
            ReviewEvent(
                row["id"], action, str(row["schema"]), datetime.now(UTC).strftime("%H:%M:%S")
            )
        )

    def _reload(self, index: int) -> None:
        refreshed = get_candidate(self.conn, self.rows[index]["id"])
        if refreshed is not None:
            self.rows[index] = refreshed

    def stage(self, extraction: Extraction) -> None:
        validate_extraction(extraction)
        self.staged = extraction

    def save_edits(self) -> bool:
        """Save staged edits to the current candidate; returns whether there were any."""
        row = self.current
        if row is None or self.staged is None:
            return False
        update_candidate_extraction(self.conn, row["id"], self.staged)
        self.staged = None
        self._reload(self.index)
        self._log(row, "e")
        return True

    def decide(self, action: str) -> None:
        """Approve (``x``), reject (``n``) or skip (``u``) the current candidate."""
        row = self.current
        if row is None:
            return
        if action == "x":
            self.save_edits()
        self.staged = None
        self.decisions.append(
            Decision(
                self.index, row["id"], action, row["status"], row["reviewer"], row["reviewed_at"]
            )
        )
        if action in ("x", "n"):
            review_candidate(self.conn, row["id"], "approved" if action == "x" else "rejected")
        self._log(row, action)
        self.index += 1

    def undo(self) -> bool:
        """Undo the last decision and go back to its candidate; edits it saved stay."""
        if not self.decisions:
            return False
        decision = self.decisions.pop()
        if decision.action in ("x", "n"):
            restore_review(
                self.conn,
                decision.candidate_id,
                decision.status,
                decision.reviewer,
                decision.reviewed_at,
            )
        self.staged = None
        self.index = decision.index
        self._reload(self.index)
        self._log(self.rows[self.index], "z")
        return True

    def progress(self) -> str:
        position = min(self.index + 1, self.total)
        parts = [
            f"Candidate {position} of {self.total}",
            f"this session: {self.count('x')} approved, {self.count('n')} rejected, "
            f"{self.count('u')} skipped",
        ]
        if self.pool is not None:
            counts = sample_results(self.conn, dataset_name=self.dataset_name)[self.pool]
            decided, right = counts["decided"], counts["approved_unedited"]
            share = f" ({right / decided:.0%})" if decided else ""
            parts.append(
                f"auto-{self.pool} sample: {decided} of {counts['sampled']} decided, "
                f"approved unedited {right}/{decided}{share}"
            )
        if self.staged is not None:
            parts.append("unsaved edits (ctrl+s saves, x saves and approves)")
        return "  ·  ".join(parts)


def ref_options(extraction: Extraction, exclude: int | None = None) -> list[tuple[str, str]]:
    """(label, key) for each entity that can be pointed to."""
    return [
        (f"{entity.get('schema')}: {entity_name(entity)}", entity["key"])
        for index, entity in enumerate(extraction)
        if index != exclude and entity.get("key")
    ]


def entity_details(extraction: Extraction, entity: dict[str, Any]) -> str:
    parts = []
    for prop, values in entity.get("properties", {}).items():
        if prop == "name":
            continue
        shown = [describe_ref(extraction, v) if v.startswith("$ref:") else v for v in values]
        parts.append(f"{prop}: {' | '.join(shown)}")
    return "; ".join(parts)


def field_row(label: str, widget: Input | Select[str]) -> Horizontal:
    """One labelled field on a single line, so a dialog fits a small terminal."""
    return Horizontal(Label(label, classes="field-label"), widget, classes="field-row")


class EntityForm(ModalScreen[dict[str, Any] | None]):
    """Edit or add one entity: its schema, and a field for each property."""

    BINDINGS = [("ctrl+s", "save", "Save"), ("escape", "cancel", "Cancel")]

    def __init__(self, entity: dict[str, Any], refs: list[tuple[str, str]], title: str):
        super().__init__()
        self.entity = entity
        self.refs = refs
        self.heading = title

    def compose(self) -> ComposeResult:
        schema = self.entity.get("schema", "Person")
        schemas = list(EXTRACTION_SCHEMAS)
        if schema not in schemas:
            schemas.append(schema)
        with Vertical(id="form-dialog", classes="dialog"):
            yield Label(self.heading, classes="dialog-title")
            yield field_row(
                "schema",
                Select(
                    [(s, s) for s in schemas],
                    value=schema,
                    allow_blank=False,
                    compact=True,
                    id="form-schema",
                ),
            )
            yield VerticalScroll(id="form-fields")
            yield Label("Separate several values with |.")
            yield Label("", id="form-error", classes="dialog-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Save", variant="primary", id="form-save")
                yield Button("Cancel", id="form-cancel")
            yield Label(DIALOG_HINT, classes="dialog-hint")

    async def on_mount(self) -> None:
        await self._show_fields(self.entity)

    async def _show_fields(self, entity: dict[str, Any]) -> None:
        fields = self.query_one("#form-fields", VerticalScroll)
        await fields.remove_children()
        schema = entity.get("schema", "Person")
        props = entity.get("properties", {})
        rows: list[Horizontal] = []
        for prop in form_fields(entity):
            values = props.get(prop, [])
            widget: Input | Select[str]
            if is_ref_property(schema, prop):
                keys = [v[5:] for v in values if v.startswith("$ref:")]
                known = {key for _, key in self.refs}
                current = keys[0] if keys and keys[0] in known else Select.NULL
                widget = Select(self.refs, value=current, compact=True, id=f"form-field-{prop}")
            else:
                widget = Input(" | ".join(values), compact=True, id=f"form-field-{prop}")
            rows.append(field_row(prop, widget))
        await fields.mount_all(rows)

    def _entity(self) -> dict[str, Any]:
        schema = self.query_one("#form-schema", Select).value
        props: dict[str, list[str]] = {}
        for widget in self.query_one("#form-fields", VerticalScroll).query("Input, Select"):
            if widget.id is None or not widget.id.startswith("form-field-"):
                continue
            prop = widget.id[len("form-field-") :]
            if isinstance(widget, Select):
                if widget.value is not Select.NULL:
                    props[prop] = [f"$ref:{widget.value}"]
            elif isinstance(widget, Input):
                values = [v.strip() for v in widget.value.split("|") if v.strip()]
                if values:
                    props[prop] = values
        entity: dict[str, Any] = {"schema": str(schema), "properties": props}
        if self.entity.get("key"):
            entity["key"] = self.entity["key"]
        return entity

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "form-schema":
            await self._show_fields(self._entity())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-save":
            self.action_save()
        else:
            self.action_cancel()

    def action_save(self) -> None:
        entity = self._entity()
        if not entity["properties"]:
            self.query_one("#form-error", Label).update("Fill in at least one property.")
            return
        self.dismiss(entity)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SplitForm(ModalScreen[tuple[str, str, str, str] | None]):
    """Split one entity into a Person, a body and the Employment linking them."""

    BINDINGS = [
        ("ctrl+s", "save", "Split"),
        ("ctrl+t", "move_to_body", "Move to body"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, entity: dict[str, Any]):
        super().__init__()
        self.entity = entity

    def compose(self) -> ComposeResult:
        with Vertical(id="split-dialog", classes="dialog"):
            yield Label(
                f"Split {self.entity.get('schema')}: {entity_name(self.entity)}",
                classes="dialog-title",
            )
            yield field_row(
                "Person's name", Input(entity_name(self.entity), compact=True, id="split-person")
            )
            yield Button("Move text after cursor to body", compact=True, id="split-move")
            yield field_row("Body's name", Input("", compact=True, id="split-body"))
            yield field_row(
                "Body's schema",
                Select(
                    [(s, s) for s in BODY_SCHEMAS],
                    value="PublicBody",
                    allow_blank=False,
                    compact=True,
                    id="split-body-schema",
                ),
            )
            yield field_row("Role (optional)", Input("", compact=True, id="split-role"))
            yield Label("", id="split-error", classes="dialog-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Split", variant="primary", id="split-save")
                yield Button("Cancel", id="split-cancel")
            yield Label(
                f"{DIALOG_HINT} · Ctrl+T: move text after cursor to body", classes="dialog-hint"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "split-save":
            self.action_save()
        elif event.button.id == "split-move":
            self.action_move_to_body()
        else:
            self.action_cancel()

    def action_move_to_body(self) -> None:
        """Move the person's name from the cursor on into the body's name."""
        person = self.query_one("#split-person", Input)
        cut = person.cursor_position
        before, after = person.value[:cut], person.value[cut:]
        self.query_one("#split-body", Input).value = after.strip(SPLIT_TRIM)
        person.value = before.strip(SPLIT_TRIM)
        person.focus()

    def action_save(self) -> None:
        person = self.query_one("#split-person", Input).value.strip()
        body = self.query_one("#split-body", Input).value.strip()
        if not person or not body:
            self.query_one("#split-error", Label).update("Fill in both names.")
            return
        schema = str(self.query_one("#split-body-schema", Select).value)
        self.dismiss((person, body, schema, self.query_one("#split-role", Input).value))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDelete(ModalScreen[bool]):
    BINDINGS = [("y", "confirm", "Delete"), ("n", "cancel", "Keep"), ("escape", "cancel", "Keep")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog", classes="dialog"):
            yield Label(self.message, classes="dialog-title")
            yield Label("Anything that points to it loses that reference.")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Delete (y)", variant="error", id="confirm-delete")
                yield Button("Keep (n)", id="confirm-keep")
            yield Label(
                "Tab / Shift+Tab: next / previous button · y: delete · n / Esc: keep",
                classes="dialog-hint",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-delete")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class JsonEditor(ModalScreen[Extraction | None]):
    """Edit the whole extraction as JSON, checked as you type."""

    BINDINGS = [("ctrl+s", "save", "Save"), ("escape", "cancel", "Cancel")]

    def __init__(self, extraction: Extraction):
        super().__init__()
        self.initial = json.dumps(extraction, indent=2, sort_keys=True)

    def compose(self) -> ComposeResult:
        with Vertical(id="json-dialog", classes="dialog"):
            yield Label("Extraction JSON", classes="dialog-title")
            yield TextArea(self.initial, id="json-text")
            yield Label("Valid", id="json-error", classes="dialog-error")
            yield Label(DIALOG_HINT, classes="dialog-hint")

    def _parse(self) -> tuple[Extraction | None, str]:
        try:
            payload = json.loads(self.query_one("#json-text", TextArea).text)
            validate_extraction(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, str(exc)
        return payload, ""

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        _, error = self._parse()
        self.query_one("#json-error", Label).update(error or "Valid")

    def action_save(self) -> None:
        payload, error = self._parse()
        if payload is None:
            self.query_one("#json-error", Label).update(error)
            return
        self.dismiss(payload)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HistoryPanel(Static):
    def reload(self, events: list[ReviewEvent]) -> None:
        table = Table(expand=True, box=None)
        table.add_column("When", style="bright_black", width=9)
        table.add_column("ID", width=7)
        table.add_column("Action", width=8)
        table.add_column("Schema", style="bright_black")
        for event in events[-25:]:
            label, style = ACTION_LABELS.get(event.action, (event.action, "white"))
            table.add_row(
                event.when, str(event.candidate_id), Text(label, style=style), event.schema
            )
        if not events:
            table.add_row("-", "-", "-", "No actions yet")
        self.update(table)


REVIEW_BINDINGS: list[Binding | tuple[str, str] | tuple[str, str, str]] = [
    Binding("x", "approve", "Approve"),
    Binding("n", "reject", "Reject"),
    Binding("u", "skip", "Skip"),
    Binding("z", "undo", "Undo"),
    Binding("enter", "edit_entity", "Edit entity"),
    Binding("a", "add_entity", "Add"),
    Binding("d", "delete_entity", "Delete"),
    Binding("s", "split_entity", "Split"),
    Binding("e", "edit_json", "JSON"),
    Binding("ctrl+s", "save_edits", "Save edits"),
    Binding("h", "history", "History"),
    Binding("q", "quit_review", "Quit"),
]
MAIN_ACTIONS = {binding.action for binding in REVIEW_BINDINGS if isinstance(binding, Binding)}


class NERReviewApp(App[dict[str, int]]):
    TITLE = "NER review"
    CSS = """
    #review-progress { height: auto; padding: 0 1; background: $boost; }
    #review-candidate {
        height: auto; max-height: 50%; padding: 0 1; border-bottom: solid $panel;
    }
    #review-body { height: 1fr; }
    #review-entities { width: 1fr; height: 1fr; }
    HistoryPanel { width: 52; border-left: solid $panel; padding: 0 1; display: none; }
    HistoryPanel.shown { display: block; }
    EntityForm, SplitForm, ConfirmDelete, JsonEditor { align: center middle; }
    .dialog {
        background: $surface; border: thick $primary; padding: 1 2;
        width: 90; height: auto; max-height: 90%;
    }
    #form-dialog { height: 90%; }
    #form-fields { height: 1fr; }
    #json-dialog { width: 95%; height: 90%; }
    #json-text { height: 1fr; }
    .field-row { height: auto; margin-bottom: 1; }
    .field-label { width: 17; color: $text-muted; }
    .field-row > Input, .field-row > Select { width: 1fr; }
    #split-move { margin: 0 0 1 17; }
    .dialog-error { color: $error; }
    .dialog-buttons { height: auto; margin-top: 1; }
    .dialog-title { margin-bottom: 1; }
    .dialog-hint { width: 100%; color: $text-muted; margin-top: 1; }
    """

    BINDINGS = REVIEW_BINDINGS

    def __init__(self, session: ReviewSession):
        super().__init__()
        self.session = session

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # While a dialog is open, its keys are the only ones that act.
        if isinstance(self.screen, ModalScreen):
            return action not in MAIN_ACTIONS
        return True

    def compose(self) -> ComposeResult:
        yield Static(id="review-progress")
        yield Static(id="review-candidate")
        with Horizontal(id="review-body"):
            yield DataTable(id="review-entities", cursor_type="row", zebra_stripes=True)
            yield HistoryPanel()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#review-entities", DataTable)
        table.add_columns("#", "Schema", "Name", "Details")
        self.refresh_view()
        table.focus()

    def refresh_view(self, keep_row: int = 0) -> None:
        # The highlighting and the source text belong to review.py's prompt view too.
        from .review import _collect_highlight_terms, _highlight_text

        session = self.session
        self.query_one("#review-progress", Static).update(session.progress())
        row = session.current
        table = self.query_one("#review-entities", DataTable)
        table.clear()
        if row is None:
            self.query_one("#review-candidate", Static).update(
                Text("No candidates left to review.")
            )
            return
        extraction = session.extraction
        terms = [t for entity in extraction for t in _collect_highlight_terms(entity)]
        meta = Text.assemble(
            (f"Candidate #{row['id']}", "bold"),
            (f"   {row['dataset']} · {row['entity_id']} · {row['property_name']}", "bright_black"),
        )
        self.query_one("#review-candidate", Static).update(
            Group(meta, _highlight_text(str(row["source_text"]), terms))
        )
        for index, entity in enumerate(extraction, start=1):
            table.add_row(
                str(index),
                str(entity.get("schema")),
                entity_name(entity),
                entity_details(extraction, entity),
            )
        if extraction:
            table.move_cursor(row=min(keep_row, len(extraction) - 1))
        self.query_one(HistoryPanel).reload(session.events)

    def _selected(self) -> int | None:
        table = self.query_one("#review-entities", DataTable)
        if self.session.current is None or table.row_count == 0:
            return None
        return table.cursor_row

    def _stage(self, extraction: Extraction, keep_row: int = 0) -> None:
        self.session.stage(extraction)
        self.refresh_view(keep_row)

    def _after_decision(self) -> None:
        if self.session.current is None:
            self.exit(self.session.summary())
            return
        self.refresh_view()

    def action_approve(self) -> None:
        self.session.decide("x")
        self._after_decision()

    def action_reject(self) -> None:
        self.session.decide("n")
        self._after_decision()

    def action_skip(self) -> None:
        self.session.decide("u")
        self._after_decision()

    def action_undo(self) -> None:
        if self.session.undo():
            self.refresh_view()
        else:
            self.notify("Nothing to undo in this session.")

    def action_save_edits(self) -> None:
        if self.session.save_edits():
            self.notify("Edits saved.")
            self.refresh_view(self._selected() or 0)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_edit_entity()

    def action_edit_entity(self) -> None:
        index = self._selected()
        if index is None:
            return
        extraction = with_keys(self.session.extraction)

        def done(entity: dict[str, Any] | None) -> None:
            if entity is not None:
                self._stage(replace_entity(extraction, index, entity), index)

        self.push_screen(
            EntityForm(extraction[index], ref_options(extraction, exclude=index), "Edit entity"),
            done,
        )

    def action_add_entity(self) -> None:
        if self.session.current is None:
            return
        extraction = with_keys(self.session.extraction)
        number = len(extraction) + 1
        keys = {entity["key"] for entity in extraction}
        while f"k{number}" in keys:
            number += 1
        new = {"key": f"k{number}", "schema": "Person", "properties": {}}

        def done(entity: dict[str, Any] | None) -> None:
            if entity is not None:
                self._stage(add_entity(extraction, entity), len(extraction))

        self.push_screen(EntityForm(new, ref_options(extraction), "Add entity"), done)

    def action_delete_entity(self) -> None:
        index = self._selected()
        if index is None:
            return
        extraction = self.session.extraction
        entity = extraction[index]

        def done(confirmed: bool | None) -> None:
            if confirmed:
                self._stage(delete_entity(extraction, index), max(0, index - 1))

        self.push_screen(
            ConfirmDelete(f"Delete {entity.get('schema')}: {entity_name(entity)}?"), done
        )

    def action_split_entity(self) -> None:
        index = self._selected()
        if index is None:
            return
        extraction = self.session.extraction

        def done(result: tuple[str, str, str, str] | None) -> None:
            if result is not None:
                person, body, schema, role = result
                self._stage(split_entity(extraction, index, person, body, schema, role), index)

        self.push_screen(SplitForm(extraction[index]), done)

    def action_edit_json(self) -> None:
        if self.session.current is None:
            return

        def done(extraction: Extraction | None) -> None:
            if extraction is not None:
                self._stage(extraction)

        self.push_screen(JsonEditor(self.session.extraction), done)

    def action_history(self) -> None:
        self.query_one(HistoryPanel).toggle_class("shown")

    def action_quit_review(self) -> None:
        if self.session.staged is not None:
            self.notify("Unsaved edits were discarded.")
        self.exit(self.session.summary())


def run_review_app(
    conn: Connection,
    rows: list[RowMapping],
    pool: str | None = None,
    dataset_name: str | None = None,
) -> dict[str, int]:
    session = ReviewSession(conn, rows, pool=pool, dataset_name=dataset_name)
    result = NERReviewApp(session).run()
    return result if result is not None else session.summary()
