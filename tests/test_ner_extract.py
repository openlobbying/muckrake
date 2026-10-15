from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from muckrake.extract.ner import pipeline
from muckrake.extract.ner.engines.base import Extractor
from muckrake.extract.ner.pipeline import run_ner_extract
from muckrake.extract.ner.storage import (
    AUTO_REVIEWER,
    auto_review,
    export_candidates,
    get_connection,
    import_candidates,
    list_candidates,
    review_candidate,
)


class SplitOnComma(Extractor):
    """A stand-in extractor: splits "<a>, <b>", leaves anything else whole."""

    name = "split-on-comma"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, text: str) -> list[dict[str, Any]]:
        self.calls.append(text)
        return [{"schema": "Person", "properties": {"name": [part]}} for part in text.split(", ")]


@pytest.fixture
def extractor(monkeypatch: pytest.MonkeyPatch) -> SplitOnComma:
    fake = SplitOnComma()
    monkeypatch.setattr(pipeline, "get_extractor", lambda name: fake)
    return fake


def _candidates(dataset: str, status: str = "pending") -> list[Any]:
    conn = get_connection()
    try:
        return list_candidates(conn, dataset_name=dataset, status=status)
    finally:
        conn.close()


def _unique(text: str) -> str:
    # Candidates are shared across datasets by text, so keep each test's texts apart.
    return f"{text} {uuid.uuid4().hex[:6]}"


def test_each_text_is_extracted_once_across_datasets(make_dataset, extractor) -> None:
    composite = _unique("Alice Archer, Bob Baker")
    first, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    second, _ = make_dataset(
        [{"schema": "Person", "properties": {"name": [composite]}, "id": "other"}]
    )

    run_ner_extract(first, extractor_name="llm", workers=4)
    run_ner_extract(second, extractor_name="llm", workers=4)

    assert extractor.calls == [composite]
    assert len(_candidates(first)) == 1
    assert _candidates(second) == []


def test_auto_review_approves_splits_and_rejects_unsplit(make_dataset, extractor) -> None:
    composite = _unique("Carol Cole, Dan Dyer")
    whole = _unique("Department for Levelling Up: Housing")
    name, _ = make_dataset(
        [
            {"schema": "Person", "properties": {"name": [composite]}},
            {"schema": "Organization", "properties": {"name": [whole]}},
        ]
    )
    run_ner_extract(name, extractor_name="llm")

    conn = get_connection()
    try:
        assert auto_review(conn, dataset_name=name) == (1, 1)
    finally:
        conn.close()

    [approved] = _candidates(name, "approved")
    [rejected] = _candidates(name, "rejected")
    assert approved["source_text"] == composite
    assert rejected["source_text"] == whole
    assert approved["reviewer"] == rejected["reviewer"] == AUTO_REVIEWER


def test_auto_review_keeps_human_decisions(make_dataset, extractor) -> None:
    composite = _unique("Erin Eve, Finn Ford")
    name, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    run_ner_extract(name, extractor_name="llm")
    [candidate] = _candidates(name)

    conn = get_connection()
    try:
        review_candidate(conn, candidate["id"], "rejected")
        assert auto_review(conn, dataset_name=name) == (0, 0)
    finally:
        conn.close()

    [rejected] = _candidates(name, "rejected")
    assert rejected["reviewer"] == "muckrake/ner-review"


def test_export_then_import_restores_candidates_and_decisions(
    make_dataset, extractor, tmp_path
) -> None:
    composite = _unique("Gina Gold, Hal Hart")
    name, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    run_ner_extract(name, extractor_name="llm")
    conn = get_connection()
    try:
        [candidate] = list_candidates(conn, dataset_name=name)
        review_candidate(conn, candidate["id"], "approved")
        export = tmp_path / "ner.jsonl.gz"
        assert export_candidates(conn, export) >= 1

        conn.execute(text("DELETE FROM ner_candidates WHERE dataset = :d"), {"d": name})
        conn.commit()
        imported, present = import_candidates(conn, export)
        assert imported == 1
        assert import_candidates(conn, export) == (0, imported + present)
    finally:
        conn.close()

    [restored] = _candidates(name, "approved")
    assert restored["source_text"] == composite
    assert restored["reviewer"] == "muckrake/ner-review"

    # Restored texts count as extracted, so they are never sent to the model again.
    extractor.calls.clear()
    run_ner_extract(name, extractor_name="llm")
    assert extractor.calls == []
