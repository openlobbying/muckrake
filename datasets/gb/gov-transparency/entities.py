import importlib.util
import re
import sys
from pathlib import Path

try:
    from .schema import Schema
    from .types import Provenance
except ImportError:
    common_spec = importlib.util.spec_from_file_location(
        f"{__name__}.common",
        Path(__file__).with_name("common.py"),
    )
    if common_spec is None or common_spec.loader is None:
        raise RuntimeError("Could not load gov-transparency common module")
    common_module = importlib.util.module_from_spec(common_spec)
    sys.modules[common_spec.name] = common_module
    common_spec.loader.exec_module(common_module)
    Schema = common_module.load_sibling_module(__file__, __name__, "schema").Schema
    Provenance = common_module.load_sibling_module(__file__, __name__, "types").Provenance


def emit_entities(dataset, row: dict, provenance: Provenance, schema: Schema) -> int:
    person, public_body, emitted = ensure_pep_context(dataset, row, provenance)

    if schema.activity_type == "meetings":
        return emitted + emit_meeting(dataset, row, provenance, person, public_body)
    if schema.activity_type == "hospitality":
        return emitted + emit_hospitality(dataset, row, provenance, person, public_body)
    if schema.activity_type == "gifts":
        return emitted + emit_gift(dataset, row, provenance, person, public_body)
    if schema.activity_type == "travel":
        return emitted + emit_travel(dataset, row, provenance, person, public_body)
    if schema.activity_type == "outside_employment":
        return emitted + emit_outside_employment(dataset, row, provenance, person)
    raise ValueError(f"Unsupported activity_type: {schema.activity_type}")


def ensure_pep_context(dataset, row: dict, provenance: Provenance):
    person_name = row.get("subject_name", "").strip()
    if not person_name:
        raise ValueError("Cannot emit activity without subject_name")

    public_body_name = get_public_body_name(provenance)
    person = make_person(dataset, person_name, provenance)
    public_body = make_public_body(dataset, public_body_name, provenance)
    employment = make_department_employment(dataset, person, public_body, provenance)

    emitted = 0
    if emit_once(dataset, public_body):
        emitted += 1
    if emit_once(dataset, person):
        emitted += 1
    if emit_once(dataset, employment):
        emitted += 1
    return person, public_body, emitted


def emit_meeting(dataset, row: dict, provenance: Provenance, person, public_body) -> int:
    counterpart = row.get("counterpart_name", "").strip()
    event = dataset.make("Meeting")
    event.id = make_row_entity_id(dataset, "meeting", provenance, row)
    add_row_date(event, row)
    if row.get("activity_description"):
        event.add("summary", row["activity_description"])
    event.add("organizer", public_body.id)
    event.add("organizer", person.id)
    emitted = 0
    if counterpart:
        participant = make_legal_entity(dataset, counterpart, provenance)
        if emit_once(dataset, participant):
            emitted += 1
        event.add("involved", participant.id)
    event.add("topics", "gov.transparency")
    apply_source(event, provenance)
    dataset.emit(event)
    return emitted + 1


def emit_hospitality(dataset, row: dict, provenance: Provenance, person, public_body) -> int:
    hospitality_type = (row.get("activity_description") or "").strip()
    counterpart = row.get("counterpart_name", "").strip()

    event = dataset.make("Hospitality")
    event.id = make_row_entity_id(dataset, "hospitality", provenance, row)
    add_row_date(event, row)
    if hospitality_type:
        event.add("purpose", hospitality_type)
    event.add("beneficiary", person.id)
    event.add("beneficiary", public_body.id)

    emitted = 0
    if counterpart:
        participant = make_legal_entity(dataset, counterpart, provenance)
        if emit_once(dataset, participant):
            emitted += 1
        event.add("involved", participant.id)
        event.add("payer", participant.id)
        event.add("organizer", participant.id)
    if row.get("outcome"):
        event.add("notes", row["outcome"])
    add_amount(event, row)
    event.add("topics", "gov.transparency")
    apply_source(event, provenance)
    dataset.emit(event)
    return emitted + 1


def emit_gift(dataset, row: dict, provenance: Provenance, person, public_body) -> int:
    counterpart = row.get("counterpart_name", "").strip()
    gift_name = (row.get("activity_description") or "").strip()

    payment = dataset.make("Gift")
    payment.id = make_row_entity_id(dataset, "gift", provenance, row)
    add_row_date(payment, row)
    if gift_name:
        payment.add("purpose", gift_name)
    payment.add("beneficiary", person.id)
    payment.add("beneficiary", public_body.id)

    emitted = 0
    if counterpart:
        participant = make_legal_entity(dataset, counterpart, provenance)
        if emit_once(dataset, participant):
            emitted += 1
        payment.add("payer", participant.id)

    add_amount(payment, row)
    if row.get("outcome"):
        payment.add("description", row["outcome"])
    apply_source(payment, provenance)
    dataset.emit(payment)
    return emitted + 1


def emit_travel(dataset, row: dict, provenance: Provenance, person, public_body) -> int:
    destination = row.get("location", "").strip()

    event = dataset.make("Trip")
    event.id = make_row_entity_id(dataset, "travel", provenance, row)
    add_row_date(event, row)
    if row.get("activity_description"):
        event.add("summary", row["activity_description"])
    if destination:
        event.add("location", destination)
    event.add("involved", public_body.id)
    event.add("involved", person.id)
    if row.get("amount"):
        event.add("notes", row["amount"])
    event.add("topics", "gov.transparency")
    apply_source(event, provenance)
    dataset.emit(event)
    return 1


def emit_outside_employment(dataset, row: dict, provenance: Provenance, person) -> int:
    employer_name = row.get("counterpart_name", "").strip() or row.get("activity_description", "").strip()
    if not employer_name:
        raise ValueError("Outside employment rows require employer details")

    employer = make_organization(dataset, employer_name, provenance)
    employment = dataset.make("Employment")
    employment.id = make_row_entity_id(dataset, "outside-employment", provenance, row)
    employment.add("employee", person.id)
    employment.add("employer", employer.id)
    if row.get("activity_description"):
        employment.add("description", row["activity_description"])
    add_row_date(employment, row)
    apply_source(employment, provenance)

    emitted = 0
    if emit_once(dataset, employer):
        emitted += 1
    dataset.emit(employment)
    return emitted + 1


def make_person(dataset, name: str, provenance: Provenance):
    person = dataset.make("Person")
    person.id = dataset.make_id("person", name)
    person.add("name", name)
    person.add("topics", "role.pep")
    person.add("jurisdiction", "gb")
    return person


def make_public_body(dataset, name: str, provenance: Provenance):
    public_body = dataset.make("PublicBody")
    public_body.id = dataset.make_id("public-body", name)
    public_body.add("name", name)
    public_body.add("jurisdiction", "gb")
    public_body.add("topics", "gov")
    return public_body


def make_department_employment(dataset, person, public_body, provenance: Provenance):
    employment = dataset.make("Employment")
    employment.id = dataset.make_id("employment", person.id, public_body.id)
    employment.add("employee", person.id)
    employment.add("employer", public_body.id)
    return employment


def make_legal_entity(dataset, name: str, provenance: Provenance):
    participant = dataset.make("LegalEntity")
    participant.id = dataset.make_id("participant", name)
    participant.add("name", name)
    return participant


def make_organization(dataset, name: str, provenance: Provenance):
    organization = dataset.make("Organization")
    organization.id = dataset.make_id("organization", name)
    organization.add("name", name)
    organization.add("jurisdiction", "gb")
    organization.add("sourceUrl", provenance.url)
    return organization


def get_public_body_name(provenance: Provenance) -> str:
    if provenance.department.strip():
        return provenance.department.strip()
    if ":" in provenance.publication_title:
        prefix = provenance.publication_title.split(":", 1)[0].strip()
        if prefix:
            return prefix
    if provenance.collection_type.strip():
        return provenance.collection_type.replace("-", " ").title()
    raise ValueError("Cannot determine public body name from provenance")


def emit_once(dataset, entity) -> bool:
    emitted_ids = getattr(dataset, "_gov_transparency_emitted_ids", None)
    if emitted_ids is None:
        emitted_ids = set()
        setattr(dataset, "_gov_transparency_emitted_ids", emitted_ids)
    if entity.id in emitted_ids:
        return False
    dataset.emit(entity)
    emitted_ids.add(entity.id)
    return True


def make_row_entity_id(dataset, prefix: str, provenance: Provenance, row: dict) -> str:
    return dataset.make_id(prefix, provenance.url, row.get("sheet_name"), row.get("row_index"))


def add_amount(entity, row: dict, *field_names: str) -> None:
    for field_name in field_names or ("amount",):
        raw = row.get(field_name, "")
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if not cleaned:
            continue
        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.replace("GBP", "").replace("gbp", "")
        cleaned = cleaned.replace("£", "").strip()
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned):
            continue
        entity.add("amount", float(cleaned))
        entity.add("currency", "GBP")
        return


def apply_source(entity, provenance: Provenance) -> None:
    entity.add("sourceUrl", provenance.url)
    entity.add("publisher", get_public_body_name(provenance))


def add_row_date(entity, row: dict) -> None:
    if row.get("date") is not None:
        entity.add("date", row["date"])
        return
    if row.get("start_date") is not None:
        entity.add("startDate", row["start_date"])
    if row.get("end_date") is not None:
        entity.add("endDate", row["end_date"])
