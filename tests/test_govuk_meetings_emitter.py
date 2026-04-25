from datasets.gb.meetings.govuk_ministerial import (
    emit_gift,
    emit_hospitality,
    emit_meeting,
    make_department,
)
from org_id import make_hashed_id


class DummyDataset:
    def __init__(self):
        self.emitted = []
        self.prefix = "gb-meet"

    def make(self, schema: str):
        from followthemoney.statement.entity import StatementEntity
        from followthemoney import Dataset as FTMDataset

        if not hasattr(self, "ftm"):
            self.ftm = FTMDataset.make({"name": "meetings", "prefix": self.prefix})
        return StatementEntity(self.ftm, {"schema": schema})

    def make_id(self, *parts, **kwargs):
        return make_hashed_id(self.prefix, *parts)

    def emit(self, entity):
        self.emitted.append(entity)


def test_emit_meeting_creates_raw_participant_entity_and_no_record_id():
    dataset = DummyDataset()
    department = make_department(dataset, "Department Example")
    record = {
        "publication_url": "https://www.gov.uk/government/publications/example",
        "source_url": "https://assets.publishing.service.gov.uk/example.csv",
        "record_index": 2,
        "period": None,
        "minister": "Minister Example",
        "date": "2024-01-10",
        "counterparty": "Google UK; OpenAI; Anthropic",
        "purpose": "Discussion about AI investment",
    }
    minister_cache = {}
    employment_cache = set()
    participant_cache = {}

    emit_meeting(
        dataset,
        department,
        "Department Example",
        record,
        minister_cache,
        employment_cache,
        participant_cache,
    )

    meeting = next(entity for entity in dataset.emitted if entity.schema.name == "Event")
    participant = next(entity for entity in dataset.emitted if entity.schema.name == "LegalEntity")

    assert participant.first("name") == "Google UK; OpenAI; Anthropic"
    assert meeting.first("summary") == "Discussion about AI investment"
    assert "recordId" not in meeting.properties
    assert participant.id in meeting.get("involved")


def test_emit_gift_uses_raw_counterparty_legal_entity():
    dataset = DummyDataset()
    department = make_department(dataset, "Department Example")
    record = {
        "publication_url": "https://www.gov.uk/government/publications/example",
        "source_url": "https://assets.publishing.service.gov.uk/example.csv",
        "record_index": 3,
        "minister": "Minister Example",
        "date": "2024-01-10",
        "gift": "Bottle of wine",
        "direction": "Received",
        "counterparty": "Example Holdings Ltd; Example Foundation",
        "value": "150",
        "outcome": "Retained by department",
    }

    emit_gift(dataset, department, "Department Example", record, {}, set(), {})

    gift = next(entity for entity in dataset.emitted if entity.schema.name == "Payment")
    participant = next(entity for entity in dataset.emitted if entity.schema.name == "LegalEntity")
    minister = next(entity for entity in dataset.emitted if entity.schema.name == "Person")

    assert participant.first("name") == "Example Holdings Ltd; Example Foundation"
    assert gift.first("payer") == participant.id
    assert gift.first("beneficiary") == minister.id
    assert gift.first("purpose") == "Bottle of wine"
    assert "recordId" not in gift.properties


def test_emit_hospitality_uses_raw_counterparty_legal_entity():
    dataset = DummyDataset()
    department = make_department(dataset, "Department Example")
    record = {
        "publication_url": "https://www.gov.uk/government/publications/example",
        "source_url": "https://assets.publishing.service.gov.uk/example.csv",
        "record_index": 4,
        "minister": "Minister Example",
        "date": "2024-01-10",
        "kind": "Dinner",
        "counterparty": "OpenAI UK Public Policy",
        "guest": "Spouse",
    }

    emit_hospitality(dataset, department, "Department Example", record, {}, set(), {})

    hospitality = next(entity for entity in dataset.emitted if entity.schema.name == "Payment")
    participant = next(entity for entity in dataset.emitted if entity.schema.name == "LegalEntity")
    minister = next(entity for entity in dataset.emitted if entity.schema.name == "Person")

    assert participant.first("name") == "OpenAI UK Public Policy"
    assert hospitality.first("payer") == participant.id
    assert hospitality.first("beneficiary") == minister.id
    assert hospitality.first("purpose") == "Dinner"
    assert "recordId" not in hospitality.properties
