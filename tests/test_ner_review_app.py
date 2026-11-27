from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from textual import events
from textual.widgets import Button, DataTable, Input, Label, TextArea

from muckrake.extract.ner.editing import (
    delete_entity,
    describe_ref,
    split_entity,
    with_keys,
)
from muckrake.extract.ner.review_app import NERReviewApp, ReviewSession
from muckrake.extract.ner.storage import (
    AUTO_REVIEWER,
    Candidate,
    draw_sample,
    get_candidate,
    get_connection,
    list_candidates,
    review_candidate,
    upsert_candidate,
)

EMPLOYMENT = [
    {"key": "p1", "schema": "Person", "properties": {"name": ["Heather Sandy"]}},
    {"key": "b1", "schema": "PublicBody", "properties": {"name": ["Lincolnshire County Council"]}},
    {
        "key": "e1",
        "schema": "Employment",
        "properties": {"employee": ["$ref:p1"], "employer": ["$ref:b1"], "role": ["Leader"]},
    },
]


def _auto_approved(extractions: list[list[dict[str, Any]]]) -> str:
    """Insert one auto-approved candidate per extraction in a new dataset; returns its name."""
    dataset = f"ds_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        for number, extraction in enumerate(extractions):
            source = f"Source text {number} {uuid.uuid4().hex[:6]}"
            upsert_candidate(
                conn,
                Candidate(
                    dataset=dataset,
                    entity_id=f"e{number}",
                    schema="LegalEntity",
                    property_name="name",
                    source_text=source,
                    fingerprint=uuid.uuid4().hex,
                    extractor="test",
                    extractor_version="1",
                    extraction=extraction,
                ),
            )
        for row in list_candidates(conn, dataset_name=dataset):
            review_candidate(conn, row["id"], "approved", reviewer=AUTO_REVIEWER)
    finally:
        conn.close()
    return dataset


def _review(
    dataset: str,
    steps: Callable[[NERReviewApp, Any], Awaitable[None]],
    pool: str | None = None,
    size: tuple[int, int] = (140, 40),
) -> ReviewSession:
    """Run the review screen on a dataset's approved candidates and play ``steps``."""
    conn = get_connection()
    if pool is not None:
        draw_sample(conn, 100, pool=pool, dataset_name=dataset)
    rows = list_candidates(conn, dataset_name=dataset, status="approved")
    session = ReviewSession(conn, rows, pool=pool, dataset_name=dataset)

    async def run() -> None:
        app = NERReviewApp(session)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await steps(app, pilot)

    try:
        asyncio.run(run())
    finally:
        conn.close()
    return session


def _row(candidate_id: int) -> Any:
    conn = get_connection()
    try:
        return get_candidate(conn, candidate_id)
    finally:
        conn.close()


def test_describe_ref_names_the_target() -> None:
    assert describe_ref(EMPLOYMENT, "$ref:p1") == "→ Person: Heather Sandy"
    assert describe_ref(EMPLOYMENT, "$ref:zz") == "→ ? (zz)"


def test_delete_drops_refs_to_the_entity() -> None:
    result = delete_entity(EMPLOYMENT, 1)
    assert [e["schema"] for e in result] == ["Person", "Employment"]
    assert result[1]["properties"] == {"employee": ["$ref:p1"], "role": ["Leader"]}


def test_split_links_person_and_body() -> None:
    whole = [{"schema": "Person", "properties": {"name": ["Heather Sandy Lincolnshire"]}}]
    result = split_entity(whole, 0, "Heather Sandy", "Lincolnshire", "PublicBody", "Councillor")
    person, body, employment = result
    assert (person["schema"], person["properties"]["name"]) == ("Person", ["Heather Sandy"])
    assert (body["schema"], body["properties"]["name"]) == ("PublicBody", ["Lincolnshire"])
    assert employment["properties"] == {
        "employee": [f"$ref:{person['key']}"],
        "employer": [f"$ref:{body['key']}"],
        "role": ["Councillor"],
    }
    assert len({person["key"], body["key"], employment["key"]}) == 3


def test_with_keys_keeps_existing_keys_and_fills_gaps() -> None:
    keyed = with_keys([{"key": "k1", "schema": "Person"}, {"schema": "Company"}])
    assert [e["key"] for e in keyed] == ["k1", "k2"]


def test_arrow_keys_move_between_entities() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        table = app.query_one("#review-entities", DataTable)
        assert table.row_count == 3
        await pilot.press("down", "down")
        assert table.cursor_row == 2
        await pilot.press("up")
        assert table.cursor_row == 1

    _review(dataset, steps)


def test_refs_are_shown_as_the_entity_they_point_to() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        table = app.query_one("#review-entities", DataTable)
        details = str(table.get_row_at(2)[3])
        assert "→ Person: Heather Sandy" in details
        assert "$ref" not in details

    _review(dataset, steps)


def test_form_edit_then_approve_is_an_edited_approval() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("enter")
        await pilot.pause()
        app.screen.query_one("#form-field-name", Input).value = "Heather J Sandy"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "unsaved edits" in app.session.progress()
        await pilot.press("x")

    session = _review(dataset, steps)
    row = _row(session.rows[0]["id"])
    assert row["status"] == "approved" and row["reviewer"] != AUTO_REVIEWER
    assert row["edited_at"] is not None
    assert json.loads(row["original_extraction_json"]) == EMPLOYMENT
    assert json.loads(row["extraction_json"])[0]["properties"]["name"] == ["Heather J Sandy"]


def test_unsaved_edits_are_not_written_without_saving() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("enter")
        await pilot.pause()
        app.screen.query_one("#form-field-name", Input).value = "Someone Else"
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("n")

    session = _review(dataset, steps)
    row = _row(session.rows[0]["id"])
    assert row["status"] == "rejected"
    assert row["edited_at"] is None
    assert json.loads(row["extraction_json"]) == EMPLOYMENT


def test_delete_asks_first_and_drops_refs() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("down", "d")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert len(app.session.extraction) == 3
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        extraction = app.session.extraction
        assert [e["schema"] for e in extraction] == ["Person", "Employment"]
        assert "employer" not in extraction[1]["properties"]

    _review(dataset, steps)


def test_add_entity_appends_it() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("a")
        await pilot.pause()
        app.screen.query_one("#form-field-name", Input).value = "Bob Baker"
        await pilot.press("ctrl+s")
        await pilot.pause()
        added = app.session.extraction[-1]
        assert (added["schema"], added["properties"]) == ("Person", {"name": ["Bob Baker"]})
        assert app.query_one("#review-entities", DataTable).row_count == 4

    _review(dataset, steps)


def test_split_produces_person_body_and_employment() -> None:
    whole = [{"schema": "Person", "properties": {"name": ["Heather Sandy Lincolnshire"]}}]
    dataset = _auto_approved([whole])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("s")
        await pilot.pause()
        app.screen.query_one("#split-person", Input).value = "Heather Sandy"
        app.screen.query_one("#split-body", Input).value = "Lincolnshire"
        app.screen.query_one("#split-role", Input).value = "Councillor"
        await pilot.press("ctrl+s")
        await pilot.pause()
        person, body, employment = app.session.extraction
        assert employment["properties"]["employee"] == [f"$ref:{person['key']}"]
        assert employment["properties"]["employer"] == [f"$ref:{body['key']}"]
        assert body["schema"] == "PublicBody"
        await pilot.press("x")

    session = _review(dataset, steps)
    assert len(json.loads(_row(session.rows[0]["id"])["extraction_json"])) == 3


def test_json_editor_rejects_invalid_input_and_saves_valid() -> None:
    dataset = _auto_approved([EMPLOYMENT])
    fixed = [{"schema": "Person", "properties": {"name": ["Heather Sandy"]}}]

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("e")
        await pilot.pause()
        editor = app.screen.query_one("#json-text", TextArea)
        editor.text = '[{"schema": "Person"}]'
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "properties" in str(app.screen.query_one("#json-error", Label).render())
        assert app.session.staged is None
        editor.text = json.dumps(fixed)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.session.extraction == fixed

    _review(dataset, steps)


def test_undo_restores_the_previous_decision() -> None:
    dataset = _auto_approved([EMPLOYMENT, EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("n")
        await pilot.pause()
        assert app.session.index == 1
        await pilot.press("z")
        await pilot.pause()
        assert app.session.index == 0

    session = _review(dataset, steps)
    row = _row(session.rows[0]["id"])
    assert (row["status"], row["reviewer"]) == ("approved", AUTO_REVIEWER)


def test_progress_line_counts_the_sample() -> None:
    dataset = _auto_approved([EMPLOYMENT, EMPLOYMENT, EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        assert "Candidate 1 of 3" in app.session.progress()
        assert "0 of 3 decided" in app.session.progress()
        await pilot.press("x")
        await pilot.pause()
        progress = app.session.progress()
        assert "Candidate 2 of 3" in progress
        assert "1 of 3 decided, approved unedited 1/1 (100%)" in progress

    _review(dataset, steps, pool="approved")


def test_progress_line_splits_the_sample_by_reviewer() -> None:
    dataset = _auto_approved([EMPLOYMENT, EMPLOYMENT, EMPLOYMENT])
    conn = get_connection()
    try:
        draw_sample(conn, 3, dataset_name=dataset)
        [first, *_] = list_candidates(conn, dataset_name=dataset, status="approved")
        review_candidate(conn, first["id"], "rejected", reviewer="claude/ner-review")
    finally:
        conn.close()

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        # Only one reviewer has decided so far: one figure, as before.
        assert "1 of 3 decided, approved unedited 0/1 (0%)" in app.session.progress()
        await pilot.press("x")
        await pilot.pause()
        progress = app.session.progress()
        assert "2 of 3 decided" in progress
        assert "claude/ner-review 0/1 (0%), muckrake/ner-review 1/1 (100%)" in progress

    _review(dataset, steps, pool="approved")


WHOLE = [{"schema": "Person", "properties": {"name": ["Heather Sandy Lincolnshire"]}}]
PERSON_WITH_FIELDS = [
    {
        "key": "p1",
        "schema": "Person",
        "properties": {
            "name": ["Heather Sandy"],
            "alias": ["H Sandy"],
            "title": ["Cllr"],
            "position": ["Leader"],
        },
    },
    *EMPLOYMENT[1:],
]


@pytest.mark.parametrize("rows", [30, 50])
def test_every_dialog_fits_the_terminal(rows: int) -> None:
    dataset = _auto_approved([PERSON_WITH_FIELDS])

    def check_fits(app: NERReviewApp, name: str) -> None:
        dialog = app.screen.query_one(".dialog")
        widgets = list(app.screen.query("Input, Select, TextArea, Button"))
        assert widgets, name
        for widget in widgets:
            region = widget.region
            assert widget.display and region.height >= 1, (name, widget.id, region)
            assert dialog.region.contains_region(region), (name, widget.id, region)
            assert 0 <= region.y and region.bottom <= rows, (name, widget.id, region)

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        for keys, name in [
            (["enter"], "edit person"),
            (["down", "down", "enter"], "edit employment"),
            (["a"], "add"),
            (["home", "s"], "split"),
            (["d"], "delete"),
            (["e"], "json"),
        ]:
            await pilot.press(*keys)
            await pilot.pause()
            check_fits(app, name)
            await pilot.press("escape")
            await pilot.pause()

    _review(dataset, steps, size=(100, rows))


@pytest.mark.parametrize(
    ("name", "person", "body"),
    [
        ("Heather Sandy Lincolnshire", "Heather Sandy", "Lincolnshire"),
        ("Heather Sandy, Lincolnshire", "Heather Sandy", "Lincolnshire"),
        (
            "Heather Sandy – Lincolnshire County Council",
            "Heather Sandy",
            "Lincolnshire County Council",
        ),
    ],
)
def test_ctrl_t_moves_text_after_the_cursor_to_the_body(name: str, person: str, body: str) -> None:
    dataset = _auto_approved([[{"schema": "Person", "properties": {"name": [name]}}]])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("s")
        await pilot.pause()
        person_input = app.screen.query_one("#split-person", Input)
        person_input.focus()
        person_input.cursor_position = len("Heather Sandy")
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert person_input.value == person
        assert app.screen.query_one("#split-body", Input).value == body

    _review(dataset, steps)


def test_move_button_splits_at_the_cursor() -> None:
    dataset = _auto_approved([WHOLE])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("s")
        await pilot.pause()
        person_input = app.screen.query_one("#split-person", Input)
        person_input.cursor_position = len("Heather Sandy")
        app.screen.query_one("#split-move", Button).press()
        await pilot.pause()
        assert person_input.value == "Heather Sandy"
        assert app.screen.query_one("#split-body", Input).value == "Lincolnshire"

    _review(dataset, steps)


def test_inputs_select_copy_cut_and_paste() -> None:
    dataset = _auto_approved([EMPLOYMENT])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("enter")
        await pilot.pause()
        name = app.screen.query_one("#form-field-name", Input)
        name.focus()
        # Focusing an input selects all its text, so go to the end first.
        await pilot.press("end", *["shift+left"] * len("Sandy"), "ctrl+c")
        assert app.clipboard == "Sandy"
        # Ctrl+C copied inside the input; it didn't reach the app's quit handling.
        assert app.is_running
        await pilot.press("end", "ctrl+v")
        assert name.value == "Heather SandySandy"
        await pilot.press(*["shift+left"] * len("Sandy"), "ctrl+x")
        assert name.value == "Heather Sandy"
        # A terminal paste (Cmd+V in macOS terminals) arrives at the app as a bracketed
        # paste, which goes to the focused widget.
        app.post_message(events.Paste(" Jr"))
        await pilot.pause()
        assert name.value == "Heather Sandy Jr"

    _review(dataset, steps)


def test_json_editor_selects_copies_and_pastes() -> None:
    dataset = _auto_approved([WHOLE])

    async def steps(app: NERReviewApp, pilot: Any) -> None:
        await pilot.press("e")
        await pilot.pause()
        editor = app.screen.query_one("#json-text", TextArea)
        editor.focus()
        editor.text = "[]"
        editor.move_cursor((0, 0))
        await pilot.press("shift+right", "shift+right", "ctrl+c")
        assert app.clipboard == "[]"
        await pilot.press("end", "ctrl+v")
        assert editor.text == "[][]"
        editor.text = ""
        app.post_message(events.Paste("[]"))
        await pilot.pause()
        assert editor.text == "[]"

    _review(dataset, steps)
