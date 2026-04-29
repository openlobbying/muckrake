from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Provenance:
    department: str
    collection_type: str
    publication_title: str
    attachment_title: str
    url: str
    period_start: date | None
    period_end: date | None
