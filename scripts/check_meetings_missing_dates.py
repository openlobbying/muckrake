import csv
from collections import defaultdict
from pathlib import Path
import sys

from org_id import make_hashed_id


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datasets.gb.meetings.common import Publication, TableSource, canonical_records, detect_category, make_resource_name, parse_period, read_csv_table, read_excel_tables


PACK_PATH = ROOT / "data/datasets/meetings/statements.pack.csv"
RESOURCE_DIR = ROOT / "data/datasets/meetings/resources"


def load_missing_events() -> dict[str, dict[str, str]]:
    events: dict[str, dict[str, str]] = {}
    dated_ids: set[str] = set()

    with PACK_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entity_id = row["entity_id"]
            prop = row["prop"]
            if not prop.startswith("Event:"):
                continue
            event = events.setdefault(entity_id, {})
            if prop == "Event:sourceUrl":
                event["source_url"] = row["value"]
            elif prop == "Event:publisherUrl":
                event["publication_url"] = row["value"]
            if prop in {"Event:date", "Event:startDate", "Event:endDate"}:
                dated_ids.add(entity_id)

    return {
        event_id: event
        for event_id, event in events.items()
        if event_id not in dated_ids
        and "publication_url" in event
        and "source_url" in event
    }


def iter_source_records_for_missing_ids(missing_events: dict[str, dict[str, str]]):
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event_id, event in missing_events.items():
        grouped[(event["publication_url"], event["source_url"])].add(event_id)

    for (publication_url, source_url), event_ids in grouped.items():
        file_name = Path(source_url).name
        publication_title = Path(publication_url).name.replace("-", " ")
        publication = Publication(url=publication_url, title=publication_title, period=parse_period(publication_title))
        resource_path = RESOURCE_DIR / make_resource_name(publication, file_name)
        if not resource_path.exists():
            continue

        class DummyDataset:
            def fetch_resource(self, name: str, url: str):
                return resource_path

        try:
            if file_name.lower().endswith("csv"):
                tables = [(file_name, read_csv_table(DummyDataset(), publication, file_name, source_url))]
            else:
                tables = list(read_excel_tables(DummyDataset(), publication, file_name, source_url))
        except Exception:
            continue

        for sheet_name, frame in tables:
            if detect_category(sheet_name, file_name, source_url) != "meetings":
                continue
            source = TableSource(
                publication=publication,
                category="meetings",
                source_url=source_url,
                title=sheet_name,
                file_name=file_name,
                frame=frame,
            )
            for record in canonical_records(source):
                event_id = make_hashed_id(
                    "gb-meet",
                    "meeting",
                    record["publication_url"],
                    record["source_url"],
                    record["record_index"],
                )
                if event_id in event_ids:
                    yield event_id, record


def main():
    missing_events = load_missing_events()
    print(f"missing_events={len(missing_events)}")

    grouped: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for event_id, record in iter_source_records_for_missing_ids(missing_events):
        grouped[str(record.get("date"))].append((event_id, record))

    for raw_date, rows in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0])):
        print(f"\nraw_date={raw_date!r} count={len(rows)}")
        for event_id, record in rows[:10]:
            print(
                event_id,
                record.get("minister"),
                record.get("counterparty"),
                record.get("source_url"),
                sep=" | ",
            )

    unresolved = set(missing_events)
    for rows in grouped.values():
        for event_id, _ in rows:
            unresolved.discard(event_id)
    if unresolved:
        print(f"\nunmatched_missing_events={len(unresolved)}")
        for event_id in sorted(list(unresolved))[:20]:
            print(event_id)


if __name__ == "__main__":
    main()
