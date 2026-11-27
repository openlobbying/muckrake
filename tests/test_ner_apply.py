from __future__ import annotations

from muckrake.extract.ner.pipeline import text_fingerprint
from muckrake.extract.ner.storage import (
    Candidate,
    get_connection,
    list_candidates,
    review_candidate,
    upsert_candidate,
)
from muckrake.load import run_load
from muckrake.store import get_sql_store


def _seed_candidate(dataset_name: str, first: str, second: str, *, approve: bool) -> str:
    """Insert an NER candidate splitting "<first> and <second>" into two people.

    Returns the composite source text. Note the candidate lookup at load time is
    keyed only on (property_name, fingerprint) with no dataset filter, so each
    test must use distinct names to stay isolated (see the module docstring
    finding below).
    """
    source_text = f"{first} and {second}"
    conn = get_connection()
    try:
        upsert_candidate(
            conn,
            Candidate(
                dataset=dataset_name,
                entity_id="seed",
                schema="Person",
                property_name="name",
                source_text=source_text,
                fingerprint=text_fingerprint(source_text),
                extractor="test",
                extractor_version="1",
                extraction=[
                    {"schema": "Person", "properties": {"name": [first]}},
                    {"schema": "Person", "properties": {"name": [second]}},
                ],
            ),
        )
        if approve:
            candidate_id = list_candidates(conn, dataset_name=dataset_name)[0]["id"]
            review_candidate(conn, candidate_id, "approved", reviewer="tester")
    finally:
        conn.close()
    return source_text


def _names(dataset_name: str) -> set[str]:
    store = get_sql_store([dataset_name])
    names: set[str] = set()
    for entity in store.view(store.dataset).entities():
        names.update(entity.get("name"))
    return names


def test_approved_candidate_is_applied_at_load(make_dataset):
    first, second = "Alice Zephyr", "Bob Quill"
    composite = f"{first} and {second}"
    name, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    _seed_candidate(name, first, second, approve=True)

    run_load(name)

    # The composite entity is replaced by the two split Person fragments.
    assert _names(name) == {first, second}


def test_pending_candidate_is_not_applied_at_load(make_dataset):
    # Distinct names from the approved test on purpose: load_approved_candidates
    # matches on (property_name, fingerprint) across ALL datasets, so reusing the
    # same composite text would let the other test's approved candidate leak in.
    # That cross-dataset coupling is itself a finding for docs#38.
    first, second = "Carol Vane", "Dave Frost"
    composite = f"{first} and {second}"
    name, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    _seed_candidate(name, first, second, approve=False)

    run_load(name)

    # Only approved candidates are applied; the original composite name survives.
    assert _names(name) == {composite}


def _seed_split(dataset_name: str, source_text: str, extraction: list[dict]) -> None:
    """Insert an approved NER candidate that splits source_text into extraction."""
    conn = get_connection()
    try:
        upsert_candidate(
            conn,
            Candidate(
                dataset=dataset_name,
                entity_id="seed",
                schema="LegalEntity",
                property_name="name",
                source_text=source_text,
                fingerprint=text_fingerprint(source_text),
                extractor="test",
                extractor_version="1",
                extraction=extraction,
            ),
        )
        row = next(r for r in list_candidates(conn) if r["source_text"] == source_text)
        review_candidate(conn, row["id"], "approved", reviewer="tester")
    finally:
        conn.close()


def _employment_split(person: str, employer: str, role: str) -> list[dict]:
    # Every split uses the same local keys, as the LLM extractor does.
    return [
        {"key": "p1", "schema": "Person", "properties": {"name": [person]}},
        {"key": "o1", "schema": "Organization", "properties": {"name": [employer]}},
        {
            "schema": "Employment",
            "properties": {"employee": ["$ref:p1"], "employer": ["$ref:o1"], "role": [role]},
        },
    ]


def _employments(dataset_name: str) -> list:
    store = get_sql_store([dataset_name])
    return [e for e in store.view(store.dataset).entities() if e.schema.name == "Employment"]


def test_splits_with_the_same_keys_give_separate_relationships(make_dataset):
    first = "Erin Kestrel, Senior Lecturer in History, Northgate University"
    second = "Femi Larch, Senior Lecturer in History, Northgate University"
    name, _ = make_dataset(
        [
            {"id": "src-first", "schema": "LegalEntity", "properties": {"name": [first]}},
            {"id": "src-second", "schema": "LegalEntity", "properties": {"name": [second]}},
        ]
    )
    for text, person in ((first, "Erin Kestrel"), (second, "Femi Larch")):
        _seed_split(
            name,
            text,
            _employment_split(person, "Northgate University", "Senior Lecturer in History"),
        )

    run_load(name)

    employments = _employments(name)
    assert len(employments) == 2
    assert all(len(e.get("employee")) == 1 for e in employments)


def test_the_same_relationship_from_two_entities_stays_one(make_dataset):
    text = "Gina Moss, Director, Harbour Trust"
    name, _ = make_dataset(
        [
            {"id": "src-a", "schema": "LegalEntity", "properties": {"name": [text]}},
            {"id": "src-b", "schema": "LegalEntity", "properties": {"name": [text]}},
        ]
    )
    _seed_split(name, text, _employment_split("Gina Moss", "Harbour Trust", "Director"))

    run_load(name)

    employments = _employments(name)
    assert len(employments) == 1
    assert len(employments[0].get("employee")) == 1
