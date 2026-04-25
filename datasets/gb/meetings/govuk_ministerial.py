from datetime import date

from collections.abc import Iterable

from .common import (
    Period,
    canonical_records,
    clean_text,
    extract_amount,
    iter_publication_tables,
    parse_cell_date,
    parse_month_value,
    parse_range_dates,
)


def make_department(dataset, department_name: str):
    department = dataset.make("PublicBody")
    department.id = dataset.make_id("department", department_name)
    department.add("name", department_name)
    department.add("jurisdiction", "gb")
    department.add("topics", "gov")
    dataset.emit(department)
    return department


def make_minister(dataset, department, name: str, minister_cache: dict[str, object], employment_cache: set[str]):
    cached = minister_cache.get(name)
    if cached is not None:
        return cached

    minister = dataset.make("Person")
    minister.id = dataset.make_id("minister", name)
    minister.add("name", name)
    minister.add("jurisdiction", "gb")
    minister.add("topics", "role.pep")
    dataset.emit(minister)

    employment_id = dataset.make_id("employment", minister.id, department.id)
    if employment_id not in employment_cache:
        employment = dataset.make("Employment")
        employment.id = employment_id
        employment.add("employee", minister.id)
        employment.add("employer", department.id)
        dataset.emit(employment)
        employment_cache.add(employment_id)

    minister_cache[name] = minister
    return minister


def make_participant(dataset, name: str, participant_cache: dict[str, object]):
    cached = participant_cache.get(name)
    if cached is not None:
        return cached

    participant = dataset.make("LegalEntity")
    participant.id = dataset.make_id("participant", name)
    participant.add("name", name)
    dataset.emit(participant)
    participant_cache[name] = participant
    return participant


def add_raw_counterparty_payment_side(payment, minister, participant, direction: str | None):
    direction_lower = (direction or "").lower()
    if "given" in direction_lower:
        payment.add("payer", minister)
        payment.add("beneficiary", participant)
        return
    payment.add("payer", participant)
    payment.add("beneficiary", minister)


def apply_source(entity, record, department_name: str):
    entity.add("sourceUrl", record["source_url"])
    entity.add("publisher", department_name)
    entity.add("publisherUrl", record["publication_url"])


def record_in_date_range(record, start_date: date | None, end_date: date | None) -> bool:
    if start_date is None and end_date is None:
        return True

    dates = []
    for field in ("date", "start_date", "end_date"):
        parsed = parse_cell_date(record.get(field))
        if parsed is not None:
            if isinstance(parsed, str):
                try:
                    parsed = date.fromisoformat(parsed)
                except ValueError:
                    continue
            dates.append(parsed)

    if not dates:
        period = record.get("period")
        if period is None:
            return True
        dates.extend([period.start, period.end])

    if start_date is not None and all(record_date < start_date for record_date in dates):
        return False
    if end_date is not None and all(record_date >= end_date for record_date in dates):
        return False
    return True


def apply_meeting_date(event, raw_date, period: Period | None):
    exact = parse_cell_date(raw_date)
    if exact is not None:
        event.add("date", exact)
        return
    text = clean_text(raw_date)
    if text is None:
        return
    month_range = parse_month_value(text, period)
    if month_range is not None:
        start_date, end_date = month_range
        event.add("startDate", start_date)
        event.add("endDate", end_date)


def emit_meeting(dataset, department, department_name: str, record, minister_cache, employment_cache, participant_cache):
    minister_name = clean_text(record.get("minister"))
    purpose = clean_text(record.get("purpose"))
    counterparty_text = clean_text(record.get("counterparty"))
    if minister_name is None or (purpose is None and counterparty_text is None):
        return

    minister = make_minister(dataset, department, minister_name, minister_cache, employment_cache)
    meeting = dataset.make("Event")
    meeting.id = dataset.make_id(
        "meeting",
        record["publication_url"],
        record["source_url"],
        record["record_index"],
    )
    meeting.add("name", f"Meeting: {minister_name}")
    apply_meeting_date(meeting, record.get("date"), record.get("period"))
    meeting.add("organizer", department.id)
    meeting.add("organizer", minister.id)
    meeting.add("keywords", "Meeting")
    meeting.add("topics", "gov")
    if purpose is not None:
        meeting.add("summary", purpose)
    if counterparty_text is not None:
        participant = make_participant(dataset, counterparty_text, participant_cache)
        meeting.add("involved", participant)
    apply_source(meeting, record, department_name)
    dataset.emit(meeting)


def emit_gift(dataset, department, department_name: str, record, minister_cache, employment_cache, participant_cache):
    minister_name = clean_text(record.get("minister"))
    gift_name = clean_text(record.get("gift"))
    direction = clean_text(record.get("direction"))
    if minister_name is None or gift_name is None:
        return

    minister = make_minister(dataset, department, minister_name, minister_cache, employment_cache)
    gift = dataset.make("Payment")
    gift.id = dataset.make_id(
        "gift",
        record["publication_url"],
        record["source_url"],
        record["record_index"],
    )
    gift.add("date", parse_cell_date(record.get("date")))
    gift.add("summary", f"Ministerial gift involving {minister_name}")
    gift.add("purpose", gift_name)

    amount = extract_amount(record.get("value"))
    if amount is not None:
        gift.add("amount", amount)
        gift.add("currency", "GBP")

    counterparty_text = clean_text(record.get("counterparty"))
    if counterparty_text is not None:
        participant = make_participant(dataset, counterparty_text, participant_cache)
        add_raw_counterparty_payment_side(gift, minister, participant, direction)
    else:
        direction_lower = (direction or "").lower()
        if "given" in direction_lower:
            gift.add("payer", minister)
        else:
            gift.add("beneficiary", minister)

    description_parts = [gift_name]
    if direction is not None:
        description_parts.append(f"Direction: {direction}")
    if counterparty_text is not None:
        description_parts.append(f"Counterparty: {counterparty_text}")
    outcome = clean_text(record.get("outcome"))
    if outcome is not None:
        description_parts.append(f"Outcome: {outcome}")
    gift.add("description", ". ".join(description_parts))
    apply_source(gift, record, department_name)
    dataset.emit(gift)


def emit_hospitality(dataset, department, department_name: str, record, minister_cache, employment_cache, participant_cache):
    minister_name = clean_text(record.get("minister"))
    hospitality_type = clean_text(record.get("kind"))
    if minister_name is None or hospitality_type is None:
        return

    minister = make_minister(dataset, department, minister_name, minister_cache, employment_cache)
    hospitality = dataset.make("Payment")
    hospitality.id = dataset.make_id(
        "hospitality",
        record["publication_url"],
        record["source_url"],
        record["record_index"],
    )
    hospitality.add("date", parse_cell_date(record.get("date")))
    hospitality.add("summary", f"Hospitality received by {minister_name}")
    hospitality.add("purpose", hospitality_type)

    description_parts = [hospitality_type]
    counterparty_text = clean_text(record.get("counterparty"))
    if counterparty_text is not None:
        participant = make_participant(dataset, counterparty_text, participant_cache)
        hospitality.add("payer", participant)
        hospitality.add("beneficiary", minister)
        description_parts.append(f"Offered by: {counterparty_text}")
    else:
        hospitality.add("beneficiary", minister)
    guest = clean_text(record.get("guest"))
    if guest is not None:
        description_parts.append(f"Guest details: {guest}")
    hospitality.add("description", ". ".join(description_parts))
    apply_source(hospitality, record, department_name)
    dataset.emit(hospitality)


def emit_travel(dataset, department, department_name: str, record, minister_cache, employment_cache):
    minister_name = clean_text(record.get("minister"))
    destination = clean_text(record.get("destination"))
    purpose = clean_text(record.get("purpose"))
    if minister_name is None or (destination is None and purpose is None):
        return

    minister = make_minister(dataset, department, minister_name, minister_cache, employment_cache)
    trip = dataset.make("Trip")
    trip.id = dataset.make_id(
        "travel",
        record["publication_url"],
        record["source_url"],
        record["record_index"],
    )
    trip.add("name", f"Overseas travel: {minister_name}")
    trip.add("organizer", department)
    trip.add("involved", minister)
    trip.add("keywords", "Overseas travel")
    trip.add("topics", "gov")
    if purpose is not None:
        trip.add("summary", purpose)
    if destination is not None:
        trip.add("location", destination)

    start_date = parse_cell_date(record.get("start_date"))
    end_date = parse_cell_date(record.get("end_date"))
    if start_date is None and end_date is None:
        start_date, end_date = parse_range_dates(record.get("date_text"), record.get("period"))
    if start_date is not None:
        trip.add("startDate", start_date)
        trip.add("date", start_date)
    if end_date is not None:
        trip.add("endDate", end_date)

    description_parts = []
    transport = clean_text(record.get("transport"))
    if transport is not None:
        description_parts.append(f"Transport: {transport}")
    transport_cost = clean_text(record.get("transport_cost"))
    if transport_cost is not None:
        description_parts.append(f"Travel cost subtotal: {transport_cost}")
    associated_cost = clean_text(record.get("associated_cost"))
    if associated_cost is not None:
        description_parts.append(f"Associated cost subtotal: {associated_cost}")
    accompanying_officials = clean_text(record.get("accompanying_officials"))
    if accompanying_officials is not None:
        description_parts.append(f"Accompanying officials: {accompanying_officials}")
    guest = clean_text(record.get("guest"))
    if guest is not None:
        description_parts.append(f"Guest details: {guest}")
    if description_parts:
        trip.add("description", ". ".join(description_parts))

    apply_source(trip, record, department_name)
    dataset.emit(trip)

    total_cost = extract_amount(record.get("total_cost"))
    if total_cost is None:
        return

    payment = dataset.make("Payment")
    payment.id = dataset.make_id(
        "travel-cost",
        record["publication_url"],
        record["source_url"],
        record["record_index"],
    )
    payment.add("payer", department)
    payment.add("beneficiary", minister)
    payment.add("amount", total_cost)
    payment.add("currency", "GBP")
    if start_date is not None:
        payment.add("date", start_date)
    payment.add("purpose", f"Ministerial overseas travel: {purpose or destination or minister_name}")
    payment.add("summary", f"Public cost of overseas travel by {minister_name}")
    if destination is not None:
        payment.add("description", destination)
    apply_source(payment, record, department_name)
    dataset.emit(payment)


def crawl_ministerial_transparency(
    dataset,
    collection_urls: str | Iterable[str],
    department_name: str,
    minister_cache: dict[str, object] | None = None,
    employment_cache: set[str] | None = None,
    participant_cache: dict[str, object] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    department = make_department(dataset, department_name)
    minister_cache = minister_cache or {}
    employment_cache = employment_cache or set()
    participant_cache = participant_cache or {}
    for source in iter_publication_tables(dataset, collection_urls):
        for record in canonical_records(source):
            if not record_in_date_range(record, start_date, end_date):
                continue
            if source.category == "meetings":
                emit_meeting(dataset, department, department_name, record, minister_cache, employment_cache, participant_cache)
            elif source.category == "gifts":
                emit_gift(dataset, department, department_name, record, minister_cache, employment_cache, participant_cache)
            elif source.category == "hospitality":
                emit_hospitality(dataset, department, department_name, record, minister_cache, employment_cache, participant_cache)
            elif source.category == "travel":
                emit_travel(dataset, department, department_name, record, minister_cache, employment_cache)
