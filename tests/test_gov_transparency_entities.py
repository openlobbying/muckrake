from datetime import date
from pathlib import Path
import importlib.util
import sys

from org_id import make_hashed_id


def load_module(name: str, relative_path: str):
    path = Path(relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


entities_module = load_module("gov_transparency_entities", "datasets/gb/gov-transparency/entities.py")
schema_module = load_module("gov_transparency_schema_for_entities", "datasets/gb/gov-transparency/schema.py")
types_module = load_module("gov_transparency_types_for_entities", "datasets/gb/gov-transparency/types.py")

emit_entities = entities_module.emit_entities
schema_from_dict = schema_module.schema_from_dict
Provenance = types_module.Provenance


class DummyDataset:
    def __init__(self):
        self.emitted = []
        self.prefix = "gb-gov"

    def make(self, schema: str):
        from followthemoney.statement.entity import StatementEntity
        from followthemoney import Dataset as FTMDataset

        if not hasattr(self, "ftm"):
            self.ftm = FTMDataset.make({"name": "gb_gov_transparency", "prefix": self.prefix})
        return StatementEntity(self.ftm, {"schema": schema})

    def make_id(self, *parts, **kwargs):
        return make_hashed_id(self.prefix, *parts)

    def emit(self, entity):
        self.emitted.append(entity)


def test_emit_meeting_entities_uses_event_and_unknown_link():
    dataset = DummyDataset()
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "meetings",
            "columns": {"minister_name": 0},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="meetings",
        publication_title="Cabinet Office meetings",
        attachment_title="Meetings",
        url="https://example.test/meetings.csv",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
    )
    row = {
        "minister_name": "Jane Doe",
        "counterpart_raw": "Example Org",
        "purpose": "Policy discussion",
        "date": date(2024, 1, 10),
        "date_precision": "day",
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 3
    person = next(entity for entity in dataset.emitted if entity.schema.name == "Person")
    event = next(entity for entity in dataset.emitted if entity.schema.name == "Event")
    link = next(entity for entity in dataset.emitted if entity.schema.name == "UnknownLink")
    assert person.first("name") == "Jane Doe"
    assert event.first("summary") == "Example Org"
    assert person.id in event.get("involved")
    assert link.first("subject") == person.id
    assert link.first("object") == event.id


def test_emit_outside_employment_entities_creates_employment():
    dataset = DummyDataset()
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "outside_employment",
            "columns": {"minister_name": 0},
        }
    )
    provenance = Provenance(
        department="hmrc",
        collection_type="outside-employment",
        publication_title="Outside employment",
        attachment_title="Outside employment",
        url="https://example.test/outside-employment.html",
        period_start=date(2024, 4, 1),
        period_end=date(2025, 3, 31),
    )
    row = {
        "minister_name": "Jane Doe",
        "counterpart_raw": "Example Advisory Board",
        "purpose": "Board member",
        "date_from": date(2024, 4, 1),
        "date_to": date(2025, 3, 31),
        "date_precision": "quarter",
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 3
    employment = next(entity for entity in dataset.emitted if entity.schema.name == "Employment")
    assert employment.first("description") == "Board member"


def test_emit_entities_deduplicates_person_across_rows():
    dataset = DummyDataset()
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "meetings",
            "columns": {"minister_name": 0},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="meetings",
        publication_title="Cabinet Office meetings",
        attachment_title="Meetings",
        url="https://example.test/meetings.csv",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
    )
    first = {
        "minister_name": "Jane Doe",
        "counterpart_raw": "Example Org",
        "purpose": "Policy discussion",
        "date": date(2024, 1, 10),
        "date_precision": "day",
    }
    second = {
        "minister_name": "Jane Doe",
        "counterpart_raw": "Another Org",
        "purpose": "Second discussion",
        "date": date(2024, 1, 11),
        "date_precision": "day",
    }

    emit_entities(dataset, first, provenance, schema)
    emit_entities(dataset, second, provenance, schema)

    people = [entity for entity in dataset.emitted if entity.schema.name == "Person"]
    events = [entity for entity in dataset.emitted if entity.schema.name == "Event"]
    assert len(people) == 1
    assert len(events) == 2
