import logging
from dataclasses import dataclass

from muckrake.util import to_string

from .common import (
    RECORD_METADATA_FIELDS,
    TableSource,
    clean_text,
    detect_field_mapping,
    is_out_of_scope_attachment,
)

log = logging.getLogger(__name__)

REQUIRED_FIELD_GROUPS = {
    "meetings": (("minister",), ("counterparty", "purpose")),
    "gifts": (("minister",), ("gift",)),
    "hospitality": (("minister",), ("kind",)),
    "travel": (("minister",), ("destination", "purpose")),
}

def format_source_label(department_name: str, source: TableSource) -> str:
    parts = [
        f"department={department_name!r}",
        f"category={source.category}",
        f"publication={source.publication.url}",
        f"attachment={source.file_name}",
    ]
    if source.title and source.title != source.file_name:
        parts.append(f"title={source.title!r}")
    return " ".join(parts)


def format_table_label(
    department_name: str,
    publication_url: str,
    source_url: str,
    file_name: str,
    title: str | None = None,
    sheet_name: str | None = None,
) -> str:
    parts = [
        f"department={department_name!r}",
        f"publication={publication_url}",
        f"attachment={file_name}",
        f"source_url={source_url}",
    ]
    if title:
        parts.append(f"title={title!r}")
    if sheet_name:
        parts.append(f"sheet={sheet_name!r}")
    return " ".join(parts)


def required_field_gaps(category: str, field_map: dict[str, str]) -> list[str]:
    gaps: list[str] = []
    for group in REQUIRED_FIELD_GROUPS.get(category, ()):
        if not any(field in field_map for field in group):
            gaps.append("/".join(group))
    return gaps


def unmapped_columns(source: TableSource, field_map: dict[str, str]) -> list[str]:
    mapped_columns = set(field_map.values())
    columns: list[str] = []
    for column in source.frame.columns:
        if not isinstance(column, str):
            continue
        if column in mapped_columns or column.startswith("unnamed"):
            continue
        columns.append(column)
    return columns


def is_nil_record(record: dict) -> bool:
    if clean_text(record.get("minister")) is None:
        return False
    for key, value in record.items():
        if key in RECORD_METADATA_FIELDS or key == "minister":
            continue
        if clean_text(value) is not None:
            return False
    return True


def source_is_nil_only(source: TableSource, field_map: dict[str, str]) -> bool:
    minister_columns = {
        column
        for column in source.frame.columns
        if isinstance(column, str) and "minister" in column
    }
    if "minister" in field_map:
        minister_columns.add(field_map["minister"])

    saw_any_text = False
    for _, row in source.frame.iterrows():
        for column, value in row.items():
            text = to_string(value)
            if text is None:
                continue
            saw_any_text = True
            normalized = clean_text(value)
            if normalized is None:
                continue
            if column in minister_columns:
                continue
            return False
    return saw_any_text


@dataclass
class SourceValidation:
    department_name: str
    source: TableSource
    field_map: dict[str, str]
    missing_required_fields: list[str]
    unmapped_columns: list[str]
    canonical_records: int = 0
    in_range_records: int = 0
    emitted_records: int = 0
    skipped_out_of_range: int = 0
    nil_return_records: int = 0
    nil_only_source: bool = False

    @property
    def label(self) -> str:
        return format_source_label(self.department_name, self.source)


class MeetingsValidation:
    def __init__(self):
        self.collection_page_errors = 0
        self.publication_page_errors = 0
        self.attachment_read_errors = 0
        self.empty_tables = 0
        self.unknown_categories = 0
        self.ignored_unknown_categories = 0
        self.sources_seen = 0
        self.weak_field_mappings = 0
        self.sources_with_unmapped_columns = 0
        self.zero_canonical_sources = 0
        self.zero_emitted_sources = 0

    def log_collection_page_error(self, department_name: str, collection_url: str, exc: Exception) -> None:
        self.collection_page_errors += 1
        log.warning(
            "Meetings collection page error department=%r collection=%s error=%s",
            department_name,
            collection_url,
            exc,
        )

    def log_publication_page_error(self, department_name: str, publication_url: str, exc: Exception) -> None:
        self.publication_page_errors += 1
        log.warning(
            "Meetings publication page error department=%r publication=%s error=%s",
            department_name,
            publication_url,
            exc,
        )

    def log_attachment_read_error(
        self,
        department_name: str,
        publication_url: str,
        source_url: str,
        file_name: str,
        exc: Exception,
    ) -> None:
        self.attachment_read_errors += 1
        log.warning(
            "Meetings attachment read error %s error=%s",
            format_table_label(department_name, publication_url, source_url, file_name),
            exc,
        )

    def log_out_of_scope_table(
        self,
        department_name: str,
        publication_url: str,
        source_url: str,
        file_name: str,
        title: str | None = None,
        sheet_name: str | None = None,
    ) -> None:
        label = format_table_label(department_name, publication_url, source_url, file_name, title=title, sheet_name=sheet_name)
        self.ignored_unknown_categories += 1
        log.info("Meetings table skipped as out-of-scope attachment %s", label)

    def log_unknown_category(
        self,
        department_name: str,
        publication_url: str,
        source_url: str,
        file_name: str,
        title: str | None = None,
        sheet_name: str | None = None,
    ) -> None:
        if is_out_of_scope_attachment(title or "", sheet_name or "", file_name, source_url):
            self.log_out_of_scope_table(
                department_name,
                publication_url,
                source_url,
                file_name,
                title=title,
                sheet_name=sheet_name,
            )
            return
        label = format_table_label(department_name, publication_url, source_url, file_name, title=title, sheet_name=sheet_name)
        self.unknown_categories += 1
        log.warning("Meetings table skipped with unknown category %s", label)

    def log_empty_table(
        self,
        department_name: str,
        publication_url: str,
        source_url: str,
        file_name: str,
        title: str | None = None,
        sheet_name: str | None = None,
    ) -> None:
        self.empty_tables += 1
        log.warning(
            "Meetings table parsed empty %s",
            format_table_label(department_name, publication_url, source_url, file_name, title=title, sheet_name=sheet_name),
        )

    def start_source(self, department_name: str, source: TableSource) -> SourceValidation:
        self.sources_seen += 1
        field_map = detect_field_mapping(source.category, source.frame.columns)
        missing_required_fields = required_field_gaps(source.category, field_map)
        source_unmapped_columns = unmapped_columns(source, field_map)
        nil_only = source_is_nil_only(source, field_map)
        if missing_required_fields and not nil_only:
            self.weak_field_mappings += 1
            log.warning(
                "Meetings source has weak field mapping %s mapped=%s missing_required=%s columns=%s",
                format_source_label(department_name, source),
                sorted(field_map),
                missing_required_fields,
                list(source.frame.columns),
            )
        if source_unmapped_columns:
            self.sources_with_unmapped_columns += 1
        return SourceValidation(
            department_name=department_name,
            source=source,
            field_map=field_map,
            missing_required_fields=missing_required_fields,
            unmapped_columns=source_unmapped_columns,
            nil_only_source=nil_only,
        )

    def finish_source(self, validation: SourceValidation) -> None:
        extra = []
        if validation.unmapped_columns:
            extra.append(f"unmapped_columns={validation.unmapped_columns}")
        if validation.missing_required_fields:
            extra.append(f"missing_required={validation.missing_required_fields}")
        extra_text = " " + " ".join(extra) if extra else ""

        if validation.canonical_records == 0:
            if validation.nil_only_source:
                log.info(
                    "Meetings source is nil return %s mapped=%s%s",
                    validation.label,
                    sorted(validation.field_map),
                    extra_text,
                )
                return
            self.zero_canonical_sources += 1
            log.warning(
                "Meetings source produced no canonical records %s mapped=%s%s",
                validation.label,
                sorted(validation.field_map),
                extra_text,
            )
            return

        if validation.in_range_records == 0:
            log.info(
                "Meetings source had no in-range records %s canonical=%d skipped_out_of_range=%d mapped=%s%s",
                validation.label,
                validation.canonical_records,
                validation.skipped_out_of_range,
                sorted(validation.field_map),
                extra_text,
            )
            return

        if validation.emitted_records == 0 and validation.nil_return_records == validation.in_range_records:
            log.info(
                "Meetings source is nil return %s canonical=%d in_range=%d mapped=%s%s",
                validation.label,
                validation.canonical_records,
                validation.in_range_records,
                sorted(validation.field_map),
                extra_text,
            )
            return

        if validation.emitted_records == 0:
            self.zero_emitted_sources += 1
            log.warning(
                "Meetings source emitted no records %s canonical=%d in_range=%d skipped_out_of_range=%d mapped=%s%s",
                validation.label,
                validation.canonical_records,
                validation.in_range_records,
                validation.skipped_out_of_range,
                sorted(validation.field_map),
                extra_text,
            )
            return

        log.info(
            "Meetings source imported %s canonical=%d in_range=%d emitted=%d skipped_out_of_range=%d mapped=%s%s",
            validation.label,
            validation.canonical_records,
            validation.in_range_records,
            validation.emitted_records,
            validation.skipped_out_of_range,
            sorted(validation.field_map),
            extra_text,
        )

    def log_summary(self) -> None:
        log.info(
            "Meetings validation summary sources=%d unknown_categories=%d ignored_unknown_categories=%d weak_field_mappings=%d sources_with_unmapped_columns=%d zero_canonical=%d zero_emitted=%d attachment_read_errors=%d empty_tables=%d collection_page_errors=%d publication_page_errors=%d",
            self.sources_seen,
            self.unknown_categories,
            self.ignored_unknown_categories,
            self.weak_field_mappings,
            self.sources_with_unmapped_columns,
            self.zero_canonical_sources,
            self.zero_emitted_sources,
            self.attachment_read_errors,
            self.empty_tables,
            self.collection_page_errors,
            self.publication_page_errors,
        )

    @staticmethod
    def is_nil_record(record: dict) -> bool:
        return is_nil_record(record)
