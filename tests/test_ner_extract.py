from __future__ import annotations

import gzip
import json
import uuid
from typing import Any

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, inspect, text

from muckrake.cli import cli
from muckrake.db import init_database
from muckrake.extract.ner import pipeline
from muckrake.extract.ner.engines.base import Extractor
from muckrake.extract.ner.pipeline import run_ner_extract
from muckrake.extract.ner.storage import (
    AUTO_REVIEWER,
    auto_review,
    compare_extractions,
    draw_sample,
    entity_forms,
    export_candidates,
    get_connection,
    import_candidates,
    list_candidates,
    list_sample_awaiting_review,
    review_candidate,
    sample_results,
    update_candidate_extraction,
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


def _auto_reviewed_dataset(
    make_dataset, composites: list[str], whole: list[str] | None = None
) -> str:
    """A dataset whose splits are auto-approved and whose unsplit names are auto-rejected."""
    entities = [
        {"schema": "Person", "properties": {"name": [c]}, "id": f"p{i}"}
        for i, c in enumerate(composites)
    ]
    entities += [
        {"schema": "Organization", "properties": {"name": [w]}, "id": f"o{i}"}
        for i, w in enumerate(whole or [])
    ]
    name, _ = make_dataset(entities)
    run_ner_extract(name, extractor_name="llm")
    conn = get_connection()
    try:
        auto_review(conn, dataset_name=name)
    finally:
        conn.close()
    return name


def test_sample_draws_only_unsampled_auto_approved_candidates(make_dataset, extractor) -> None:
    composites = [_unique(f"Annabel Archer {i}, Benjamin Baker {i}") for i in range(4)]
    whole = [_unique("Department for Levelling Up: Housing")]
    name = _auto_reviewed_dataset(make_dataset, composites, whole=whole)
    conn = get_connection()
    try:
        # A person's decision takes a candidate out of what can be sampled.
        human = list_candidates(conn, dataset_name=name, status="approved")[0]
        review_candidate(conn, human["id"], "approved")

        assert draw_sample(conn, 2, dataset_name=name) == 2
        sampled = list_sample_awaiting_review(conn, dataset_name=name)
        assert len(sampled) == 2
        assert all(row["sampled_at"] for row in sampled)
        assert all(row["status"] == "approved" for row in sampled)
        assert human["id"] not in {row["id"] for row in sampled}

        # Only one eligible candidate is left, so a bigger draw takes just that one.
        assert draw_sample(conn, 10, dataset_name=name) == 1
        assert draw_sample(conn, 10, dataset_name=name) == 0
        assert len(list_sample_awaiting_review(conn, dataset_name=name)) == 3
        [rejected] = list_candidates(conn, dataset_name=name, status="rejected")
        assert rejected["sampled_at"] is None
        assert {row["sampled_status"] for row in sampled} == {"approved"}
    finally:
        conn.close()


def test_sample_target_is_not_overdrawn_on_rerun(make_dataset, extractor) -> None:
    composites = [_unique(f"Yara Young {i}, Zed Zane {i}") for i in range(5)]
    name = _auto_reviewed_dataset(make_dataset, composites)
    conn = get_connection()
    try:
        assert draw_sample(conn, 2, dataset_name=name) == 2
        # The same target again draws nothing, so rerunning the command resumes.
        assert draw_sample(conn, 2, dataset_name=name) == 0
        # A smaller target never shrinks the sample.
        assert draw_sample(conn, 1, dataset_name=name) == 0
        assert len(list_sample_awaiting_review(conn, dataset_name=name)) == 2
        # A bigger target tops it up to the target.
        assert draw_sample(conn, 4, dataset_name=name) == 2
        assert len(list_sample_awaiting_review(conn, dataset_name=name)) == 4
        # Decided candidates still count towards the target.
        [first, *_] = list_sample_awaiting_review(conn, dataset_name=name)
        review_candidate(conn, first["id"], "approved")
        assert draw_sample(conn, 4, dataset_name=name) == 0
    finally:
        conn.close()


def test_sample_targets_are_per_pool(make_dataset, extractor) -> None:
    composites = [_unique(f"Abel Ames {i}, Bea Bell {i}") for i in range(3)]
    whole = [_unique(f"Office number {i}: Rail") for i in range(3)]
    name = _auto_reviewed_dataset(make_dataset, composites, whole=whole)
    conn = get_connection()
    try:
        assert draw_sample(conn, 2, pool="approved", dataset_name=name) == 2
        assert draw_sample(conn, 2, pool="rejected", dataset_name=name) == 2
        assert draw_sample(conn, 2, pool="rejected", dataset_name=name) == 0
        assert draw_sample(conn, 3, pool="rejected", dataset_name=name) == 1
        assert draw_sample(conn, 2, pool="approved", dataset_name=name) == 0
        assert len(list_sample_awaiting_review(conn, pool="approved", dataset_name=name)) == 2
        assert len(list_sample_awaiting_review(conn, pool="rejected", dataset_name=name)) == 3
    finally:
        conn.close()


def test_rejected_pool_samples_only_auto_rejected_candidates(make_dataset, extractor) -> None:
    whole = [_unique(f"Department number {i}: Housing") for i in range(3)]
    name = _auto_reviewed_dataset(make_dataset, [_unique("Ivy Irons, Jack Jones")], whole=whole)
    conn = get_connection()
    try:
        assert draw_sample(conn, 2, pool="rejected", dataset_name=name) == 2
        sampled = list_sample_awaiting_review(conn, pool="rejected", dataset_name=name)
        assert len(sampled) == 2
        assert {row["status"] for row in sampled} == {"rejected"}
        assert {row["sampled_status"] for row in sampled} == {"rejected"}
        # The pools are kept apart: the approved queue is still empty.
        assert list_sample_awaiting_review(conn, pool="approved", dataset_name=name) == []
        assert draw_sample(conn, 5, pool="rejected", dataset_name=name) == 1
        with pytest.raises(ValueError):
            draw_sample(conn, 1, pool="pending", dataset_name=name)
    finally:
        conn.close()


def test_edit_records_edited_at_and_a_plain_approve_does_not(make_dataset, extractor) -> None:
    name = _auto_reviewed_dataset(
        make_dataset, [_unique("Mona Moss, Ned Nash"), _unique("Olga Oak, Pete Pine")]
    )
    conn = get_connection()
    try:
        edited, plain = list_candidates(conn, dataset_name=name, status="approved")
        update_candidate_extraction(
            conn, edited["id"], [{"schema": "Person", "properties": {"name": ["Mona Moss"]}}]
        )
        review_candidate(conn, edited["id"], "approved")
        review_candidate(conn, plain["id"], "approved")
        rows = {
            row["id"]: row for row in list_candidates(conn, dataset_name=name, status="approved")
        }
    finally:
        conn.close()
    assert rows[edited["id"]]["edited_at"]
    assert rows[plain["id"]]["edited_at"] is None


def test_sample_results_count_both_pools_after_human_review(make_dataset, extractor) -> None:
    composites = [_unique(f"Karl Kent {i}, Lena Lyle {i}") for i in range(4)]
    whole = [_unique(f"Ministry number {i}: Defence") for i in range(3)]
    name = _auto_reviewed_dataset(make_dataset, composites, whole=whole)
    split = [{"schema": "Person", "properties": {"name": ["Someone"]}}]
    conn = get_connection()
    try:
        draw_sample(conn, 4, pool="approved", dataset_name=name)
        draw_sample(conn, 3, pool="rejected", dataset_name=name)
        right, corrected, wrong, _ = list_sample_awaiting_review(
            conn, pool="approved", dataset_name=name
        )
        # A split kept as it was, one corrected and kept, one rejected; one not decided yet.
        review_candidate(conn, right["id"], "approved")
        update_candidate_extraction(conn, corrected["id"], split)
        review_candidate(conn, corrected["id"], "approved")
        review_candidate(conn, wrong["id"], "rejected")
        # A name left whole that was really composite (split, then approved), one that was
        # one entity (rejected), and one approved without an edit (not a miss).
        missed, whole_right, unedited = list_sample_awaiting_review(
            conn, pool="rejected", dataset_name=name
        )
        update_candidate_extraction(conn, missed["id"], split)
        review_candidate(conn, missed["id"], "approved")
        review_candidate(conn, whole_right["id"], "rejected")
        review_candidate(conn, unedited["id"], "approved")

        results = sample_results(conn, dataset_name=name)
    finally:
        conn.close()
    split_counts = {
        pool: {k: v for k, v in counts.items() if k != "entities"}
        for pool, counts in results.items()
    }
    assert split_counts == {
        "approved": {
            "sampled": 4,
            "decided": 3,
            "approved_unedited": 1,
            "approved_edited": 1,
            "edited_without_original": 0,
        },
        "rejected": {
            "sampled": 3,
            "decided": 3,
            "approved_unedited": 1,
            "approved_edited": 1,
            "edited_without_original": 0,
        },
    }


def test_an_edit_before_sampling_does_not_count_as_a_correction(make_dataset, extractor) -> None:
    composite = _unique("Quin Quail, Rosa Reed")
    name, _ = make_dataset([{"schema": "Person", "properties": {"name": [composite]}}])
    run_ner_extract(name, extractor_name="llm")
    conn = get_connection()
    try:
        [pending] = list_candidates(conn, dataset_name=name)
        # Edited while still pending, then decided by --auto, then sampled.
        update_candidate_extraction(
            conn, pending["id"], [{"schema": "Person", "properties": {"name": ["Quin Quail"]}}]
        )
        auto_review(conn, dataset_name=name)
        draw_sample(conn, 1, dataset_name=name)
        [sampled] = list_sample_awaiting_review(conn, dataset_name=name)
        review_candidate(conn, sampled["id"], "approved")
        results = sample_results(conn, dataset_name=name)
    finally:
        conn.close()
    assert results["approved"]["approved_unedited"] == 1
    assert results["approved"]["approved_edited"] == 0


def test_reviewed_sample_candidates_leave_the_queue(make_dataset, extractor) -> None:
    name = _auto_reviewed_dataset(make_dataset, [_unique("Cyril Cole, Diana Dee")])
    conn = get_connection()
    try:
        assert draw_sample(conn, 1, dataset_name=name) == 1
        [row] = list_sample_awaiting_review(conn, dataset_name=name)
        review_candidate(conn, row["id"], "rejected")
        assert list_sample_awaiting_review(conn, dataset_name=name) == []
        [decided] = list_candidates(conn, dataset_name=name, status="rejected")
        assert decided["sampled_at"] == row["sampled_at"]
    finally:
        conn.close()


def _person(name: str) -> dict[str, Any]:
    return {"schema": "Person", "properties": {"name": [name]}}


def test_first_edit_keeps_the_original_and_later_edits_do_not(make_dataset, extractor) -> None:
    name = _auto_reviewed_dataset(make_dataset, [_unique("Sara Shaw, Tom Todd")])
    conn = get_connection()
    try:
        [row] = list_candidates(conn, dataset_name=name, status="approved")
        assert row["original_extraction_json"] is None
        update_candidate_extraction(conn, row["id"], [_person("Sara Shaw")])
        update_candidate_extraction(conn, row["id"], [_person("Tom Todd")])
        [after] = list_candidates(conn, dataset_name=name, status="approved")
    finally:
        conn.close()
    assert json.loads(after["original_extraction_json"]) == json.loads(row["extraction_json"])
    assert json.loads(after["extraction_json"]) == [_person("Tom Todd")]


def test_entity_forms_compare_refs_by_target_not_key() -> None:
    def employment(person_key: str, org_key: str, org_name: str) -> list[dict[str, Any]]:
        return [
            {"key": person_key, "schema": "Person", "properties": {"name": ["Ann Ash"]}},
            {"key": org_key, "schema": "PublicBody", "properties": {"name": [org_name]}},
            {
                "schema": "Employment",
                "properties": {
                    "employee": [f"$ref:{person_key}"],
                    "employer": [f"$ref:{org_key}"],
                    "role": ["Leader"],
                },
            },
        ]

    original = employment("p1", "c1", "Avon Council")
    # Same entities with renamed keys and in another order: nothing changed.
    assert compare_extractions(original, list(reversed(employment("a", "b", "Avon Council")))) == (
        3,
        0,
        0,
    )
    # Renaming the body changes it and the Employment that points to it.
    assert compare_extractions(original, employment("p1", "c1", "Avon County Council")) == (1, 2, 2)
    assert sum(entity_forms(original).values()) == 3


def test_sample_results_count_entities(make_dataset, extractor) -> None:
    composites = [_unique(f"Uma Underwood {i}, Vic Vance {i}") for i in range(3)]
    whole = [_unique(f"Agency number {i}: Transport") for i in range(2)]
    name = _auto_reviewed_dataset(make_dataset, composites, whole=whole)
    conn = get_connection()
    try:
        draw_sample(conn, 3, pool="approved", dataset_name=name)
        draw_sample(conn, 2, pool="rejected", dataset_name=name)
        right, corrected, wrong = list_sample_awaiting_review(
            conn, pool="approved", dataset_name=name
        )
        # Two entities kept as they are.
        review_candidate(conn, right["id"], "approved")
        # One of two kept, one changed, one more added: kept 1, removed 1, added 2.
        first = json.loads(corrected["extraction_json"])[0]
        update_candidate_extraction(conn, corrected["id"], [first, _person("X1"), _person("X2")])
        review_candidate(conn, corrected["id"], "approved")
        # Rejecting an auto-approved split removes both its entities.
        review_candidate(conn, wrong["id"], "rejected")
        missed, kept_whole = list_sample_awaiting_review(conn, pool="rejected", dataset_name=name)
        # A name left whole that the person splits in two: removed 1, added 2.
        update_candidate_extraction(conn, missed["id"], [_person("Part A"), _person("Part B")])
        review_candidate(conn, missed["id"], "approved")
        # Rejecting an auto-rejected name keeps its single entity.
        review_candidate(conn, kept_whole["id"], "rejected")
        results = sample_results(conn, dataset_name=name)
    finally:
        conn.close()
    assert results["approved"]["entities"] == {"checked": 6, "kept": 3, "removed": 3, "added": 2}
    assert results["rejected"]["entities"] == {"checked": 2, "kept": 1, "removed": 1, "added": 2}


def test_edits_without_an_original_count_per_split_only(make_dataset, extractor) -> None:
    name = _auto_reviewed_dataset(make_dataset, [_unique("Wes Webb, Xena Xu")])
    conn = get_connection()
    try:
        draw_sample(conn, 1, dataset_name=name)
        [row] = list_sample_awaiting_review(conn, dataset_name=name)
        # As if edited before original extractions were kept: edited_at, no original.
        conn.execute(
            text("UPDATE ner_candidates SET edited_at = :now WHERE id = :id"),
            {"now": "9999-01-01T00:00:00+00:00", "id": row["id"]},
        )
        conn.commit()
        review_candidate(conn, row["id"], "approved")
        results = sample_results(conn, dataset_name=name)
    finally:
        conn.close()
    assert results["approved"]["approved_edited"] == 1
    assert results["approved"]["edited_without_original"] == 1
    assert results["approved"]["entities"] == {"checked": 0, "kept": 0, "removed": 0, "added": 0}


def test_export_and_import_carry_sampled_at(make_dataset, extractor, tmp_path) -> None:
    name = _auto_reviewed_dataset(make_dataset, [_unique("Edward Eel, Florence Fox")])
    export = tmp_path / "ner.jsonl.gz"
    conn = get_connection()
    try:
        draw_sample(conn, 1, dataset_name=name)
        [before] = list_sample_awaiting_review(conn, dataset_name=name)
        update_candidate_extraction(
            conn, before["id"], [{"schema": "Person", "properties": {"name": ["Edward Eel"]}}]
        )
        [before] = list_sample_awaiting_review(conn, dataset_name=name)
        assert before["original_extraction_json"] is not None
        export_candidates(conn, export)
        conn.execute(text("DELETE FROM ner_candidates WHERE dataset = :d"), {"d": name})
        conn.commit()
        import_candidates(conn, export)
        [after] = list_sample_awaiting_review(conn, dataset_name=name)
    finally:
        conn.close()
    assert after["sampled_at"] == before["sampled_at"]
    assert after["sampled_status"] == before["sampled_status"] == "approved"
    assert after["edited_at"] == before["edited_at"] is not None
    assert after["original_extraction_json"] == before["original_extraction_json"]


def test_import_of_an_export_without_sampled_at(make_dataset, extractor, tmp_path) -> None:
    name = _auto_reviewed_dataset(make_dataset, [_unique("Gustav Gray, Helena Hope")])
    export = tmp_path / "ner.jsonl.gz"
    conn = get_connection()
    try:
        export_candidates(conn, export)
        conn.execute(text("DELETE FROM ner_candidates WHERE dataset = :d"), {"d": name})
        conn.commit()
        old = tmp_path / "old.jsonl.gz"
        with gzip.open(export, "rt") as src, gzip.open(old, "wt") as dst:
            for line in src:
                row = json.loads(line)
                for column in ("sampled_at", "sampled_status", "edited_at"):
                    del row[column]
                del row["original_extraction_json"]
                dst.write(json.dumps(row) + "\n")
        imported, _ = import_candidates(conn, old)
        assert imported >= 1
        [restored] = list_candidates(conn, dataset_name=name, status="approved")
    finally:
        conn.close()
    assert restored["sampled_at"] is None
    assert restored["sampled_status"] is None
    assert restored["edited_at"] is None
    assert restored["original_extraction_json"] is None


def test_init_database_adds_the_sample_columns_to_an_existing_table(tmp_path) -> None:
    uri = f"sqlite:///{tmp_path / 'old.db'}"
    old = create_engine(uri)
    with old.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE ner_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset VARCHAR NOT NULL, entity_id VARCHAR NOT NULL,
                    schema VARCHAR NOT NULL, property_name VARCHAR NOT NULL,
                    source_text TEXT NOT NULL, fingerprint VARCHAR NOT NULL,
                    extractor VARCHAR NOT NULL, extractor_version VARCHAR NOT NULL,
                    status VARCHAR NOT NULL, reviewer VARCHAR, reviewed_at VARCHAR,
                    extraction_json TEXT NOT NULL, created_at VARCHAR NOT NULL,
                    updated_at VARCHAR NOT NULL
                )
                """
            )
        )
    old.dispose()

    engine = init_database(uri)
    columns = {c["name"] for c in inspect(engine).get_columns("ner_candidates")}
    engine.dispose()
    assert {"sampled_at", "sampled_status", "edited_at", "original_extraction_json"} <= columns


@pytest.mark.parametrize("other", [["--auto"], ["--limit", "5"]])
def test_sample_cannot_be_combined_with_auto_or_limit(other: list[str]) -> None:
    result = CliRunner().invoke(cli, ["ner-review", "--sample", "5", *other])
    assert result.exit_code != 0
    assert "--sample can't be combined" in result.output


def test_rejected_needs_sample() -> None:
    result = CliRunner().invoke(cli, ["ner-review", "--rejected"])
    assert result.exit_code != 0
    assert "--rejected needs --sample" in result.output
