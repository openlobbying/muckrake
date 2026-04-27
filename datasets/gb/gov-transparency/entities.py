import importlib.util
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
    if schema.activity_type in {"meetings", "gifts", "hospitality", "travel"}:
        return emit_activity_entities(dataset, row, provenance, schema)
    if schema.activity_type == "outside_employment":
        return emit_outside_employment_entities(dataset, row, provenance, schema)
    raise ValueError(f"Unsupported activity_type: {schema.activity_type}")


def emit_activity_entities(dataset, row: dict, provenance: Provenance, schema: Schema) -> int:
    minister_name = row.get("minister_name", "").strip()
    if not minister_name:
        raise ValueError("Cannot emit activity entity without minister_name")

    person = make_person(dataset, minister_name, provenance)
    emitted = 0
    if emit_once(dataset, person):
        emitted += 1

    event = dataset.make("Event")
    event.id = dataset.make_id(
        "event",
        provenance.url,
        minister_name,
        row.get("date_from") or row.get("date"),
        row.get("counterpart_raw", "")[:50],
        row.get("purpose", ""),
    )
    event.add("name", build_event_name(schema.activity_type, minister_name, row.get("counterpart_raw")))
    add_row_date(event, row)
    if row.get("purpose"):
        event.add("description", row["purpose"])
    if row.get("counterpart_raw"):
        event.add("summary", row["counterpart_raw"])
    event.add("topics", "gov.transparency")
    event.add("sourceUrl", provenance.url)
    event.add("publisher", provenance.department or provenance.collection_type)
    event.add("involved", person.id)
    dataset.emit(event)
    emitted += 1

    link = dataset.make("UnknownLink")
    link.id = dataset.make_id("event-link", person.id, event.id)
    link.add("subject", person.id)
    link.add("object", event.id)
    link.add("role", "participant")
    link.add("sourceUrl", provenance.url)
    add_row_date(link, row)
    dataset.emit(link)
    return emitted + 1


def emit_outside_employment_entities(dataset, row: dict, provenance: Provenance, schema: Schema) -> int:
    person_name = row.get("minister_name", "").strip()
    employer_name = row.get("counterpart_raw", "").strip() or row.get("purpose", "").strip()
    if not person_name or not employer_name:
        raise ValueError("Outside employment rows require person and employer details")

    person = make_person(dataset, person_name, provenance)
    employer = make_organization(dataset, employer_name, provenance)
    emitted = 0
    if emit_once(dataset, person):
        emitted += 1
    if emit_once(dataset, employer):
        emitted += 1

    employment = dataset.make("Employment")
    employment.id = dataset.make_id("employment", person.id, employer.id, provenance.url)
    employment.add("employee", person.id)
    employment.add("employer", employer.id)
    if row.get("purpose"):
        employment.add("description", row["purpose"])
    employment.add("sourceUrl", provenance.url)
    add_row_date(employment, row)
    dataset.emit(employment)
    return emitted + 1


def make_person(dataset, name: str, provenance: Provenance):
    person = dataset.make("Person")
    person.id = dataset.make_id("person", name)
    person.add("name", name)
    person.add("topics", "role.pep")
    person.add("jurisdiction", "gb")
    person.add("sourceUrl", provenance.url)
    return person


def make_organization(dataset, name: str, provenance: Provenance):
    organization = dataset.make("Organization")
    organization.id = dataset.make_id("organization", name)
    organization.add("name", name)
    organization.add("jurisdiction", "gb")
    organization.add("sourceUrl", provenance.url)
    return organization


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


def build_event_name(activity_type: str, minister_name: str, counterpart_raw: str | None) -> str:
    prefix = {
        "meetings": "Meeting",
        "gifts": "Gift",
        "hospitality": "Hospitality",
        "travel": "Travel",
    }.get(activity_type, "Activity")
    counterpart = (counterpart_raw or "").strip()
    if counterpart:
        return f"{prefix}: {minister_name} with {counterpart[:50]}"
    return f"{prefix}: {minister_name}"


def add_row_date(entity, row: dict) -> None:
    if row.get("date") is not None:
        entity.add("date", row["date"])
        entity.add("startDate", row["date"])
        return
    if row.get("date_from") is not None:
        entity.add("date", row["date_from"])
        entity.add("startDate", row["date_from"])
    if row.get("date_to") is not None:
        entity.add("endDate", row["date_to"])
