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


entities_module = load_module("gov_transparency_entities", "datasets/gb/gov_transparency/entities.py")
schema_module = load_module("gov_transparency_schema_for_entities", "datasets/gb/gov_transparency/schema.py")
types_module = load_module("gov_transparency_types_for_entities", "datasets/gb/gov_transparency/types.py")

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


def make_provenance(collection_type: str, url: str) -> Provenance:
    return Provenance(
        department="Cabinet Office",
        collection_type=collection_type,
        publication_title="Cabinet Office: transparency return",
        attachment_title=collection_type.title(),
        url=url,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
    )


def test_emit_meeting_entities_creates_person_public_body_employment_legal_entity_and_meeting():
    dataset = DummyDataset()
    schema = schema_from_dict({"fingerprint": "abc", "sheet_type": "data", "activity_type": "meetings", "mapping": {"official_name": 0}})
    provenance = make_provenance("meetings", "https://example.test/meetings.csv")
    row = {
        "official_name": "Jane Doe",
        "counterparty_name": "Example Org",
        "summary": "Policy discussion",
        "date": "2024-01-10",
        "date_precision": "day",
        "sheet_name": "Meetings",
        "row_index": 2,
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 5
    person = next(entity for entity in dataset.emitted if entity.schema.name == "Person")
    public_body = next(entity for entity in dataset.emitted if entity.schema.name == "PublicBody")
    employment = next(entity for entity in dataset.emitted if entity.schema.name == "Employment")
    participant = next(entity for entity in dataset.emitted if entity.schema.name == "LegalEntity")
    event = next(entity for entity in dataset.emitted if entity.schema.name == "Meeting")

    assert person.first("name") == "Jane Doe"
    assert public_body.first("name") == "Cabinet Office"
    assert employment.first("employee") == person.id
    assert participant.first("name") == "Example Org"
    assert event.first("summary") == "Policy discussion"
    assert sorted(event.get("organizer")) == sorted([person.id, public_body.id])
    assert event.first("involved") == participant.id


def test_emit_hospitality_entities_creates_hospitality_payment_with_participant():
    dataset = DummyDataset()
    schema = schema_from_dict({"fingerprint": "abc", "sheet_type": "data", "activity_type": "hospitality", "mapping": {"official_name": 0}})
    provenance = make_provenance("hospitality", "https://example.test/hospitality.csv")
    row = {
        "official_name": "Jane Doe",
        "counterparty_name": "Example Org",
        "summary": "Dinner",
        "outcome_text": "Accompanied by guest",
        "date": "2024-01-10",
        "date_precision": "day",
        "sheet_name": "Hospitality",
        "row_index": 4,
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 5
    event = next(entity for entity in dataset.emitted if entity.schema.name == "Hospitality")
    assert event.first("purpose") == "Dinner"
    assert event.first("involved")
    assert event.first("payer")
    assert event.first("organizer") == event.first("payer")
    assert event.first("beneficiary")


def test_emit_travel_entities_creates_trip():
    dataset = DummyDataset()
    schema = schema_from_dict({"fingerprint": "abc", "sheet_type": "data", "activity_type": "travel", "mapping": {"official_name": 0}})
    provenance = make_provenance("travel", "https://example.test/travel.csv")
    row = {
        "official_name": "Jane Doe",
        "location": "Paris",
        "summary": "Trade mission",
        "amount": "1234",
        "start_date": "2024-01-10",
        "end_date": "2024-01-10",
        "date_precision": "day",
        "sheet_name": "Travel",
        "row_index": 6,
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 4
    trip = next(entity for entity in dataset.emitted if entity.schema.name == "Trip")
    assert trip.first("summary") == "Trade mission"
    assert trip.first("location") == "Paris"
    assert trip.first("notes") == "1234"
    assert trip.get("date") == []
    assert trip.first("startDate") == "2024-01-10"
    assert trip.first("endDate") == "2024-01-10"


def test_emit_gift_entities_creates_gift_with_person_and_public_body_as_beneficiaries():
    dataset = DummyDataset()
    schema = schema_from_dict({"fingerprint": "abc", "sheet_type": "data", "activity_type": "gifts", "mapping": {"official_name": 0}})
    provenance = make_provenance("gifts", "https://example.test/gifts.csv")
    row = {
        "official_name": "Jane Doe",
        "counterparty_name": "Example Org",
        "summary": "Bottle of wine",
        "amount": "150",
        "outcome_text": "Retained by department",
        "date": "2024-01-10",
        "date_precision": "day",
        "sheet_name": "Gifts",
        "row_index": 3,
    }

    count = emit_entities(dataset, row, provenance, schema)

    assert count == 5
    person = next(entity for entity in dataset.emitted if entity.schema.name == "Person")
    public_body = next(entity for entity in dataset.emitted if entity.schema.name == "PublicBody")
    participant = next(entity for entity in dataset.emitted if entity.schema.name == "LegalEntity")
    payment = next(entity for entity in dataset.emitted if entity.schema.name == "Gift")

    assert payment.first("payer") == participant.id
    assert sorted(payment.get("beneficiary")) == sorted([person.id, public_body.id])
    assert payment.first("purpose") == "Bottle of wine"
    assert payment.first("amount") == "150.00"
    assert payment.first("currency") == "GBP"


def test_emit_entities_deduplicates_context_entities_across_rows():
    dataset = DummyDataset()
    schema = schema_from_dict({"fingerprint": "abc", "sheet_type": "data", "activity_type": "meetings", "mapping": {"official_name": 0}})
    provenance = make_provenance("meetings", "https://example.test/meetings.csv")
    first = {
        "official_name": "Jane Doe",
        "counterparty_name": "Example Org",
        "summary": "Policy discussion",
        "date": "2024-01-10",
        "date_precision": "day",
        "sheet_name": "Meetings",
        "row_index": 2,
    }
    second = {
        "official_name": "Jane Doe",
        "counterparty_name": "Another Org",
        "summary": "Second discussion",
        "date": "2024-01-11",
        "date_precision": "day",
        "sheet_name": "Meetings",
        "row_index": 3,
    }

    emit_entities(dataset, first, provenance, schema)
    emit_entities(dataset, second, provenance, schema)

    people = [entity for entity in dataset.emitted if entity.schema.name == "Person"]
    public_bodies = [entity for entity in dataset.emitted if entity.schema.name == "PublicBody"]
    employments = [entity for entity in dataset.emitted if entity.schema.name == "Employment"]
    events = [entity for entity in dataset.emitted if entity.schema.name == "Meeting"]
    participants = [entity for entity in dataset.emitted if entity.schema.name == "LegalEntity"]

    assert len(people) == 1
    assert len(public_bodies) == 1
    assert len(employments) == 1
    assert len(events) == 2
    assert len(participants) == 2
