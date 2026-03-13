# Zavod UI: Data Review Process for Extraction Quality

Zavod UI is a web application that enables human-in-the-loop review and correction of automated data extractions in the OpenSanctions pipeline. It is designed for cases where automated extraction (e.g., from LLMs, OCR, or scrapers) may not be sufficiently accurate, and human validation is required before data is accepted into the canonical database.

## Why Data Reviews?

Automated extraction can introduce errors, miss context, or misinterpret unstructured data. The data review process ensures:
- Human reviewers can fix extraction issues before acceptance.
- Only reviewed and accepted data is published or used downstream.
- Changes in source data or extraction models trigger re-review as needed.
- Data model changes are handled robustly, with incompatible changes failing early.
- User-edited data is validated early (ideally in the UI) to prevent slow review cycles.

## Review Workflow

1. **Define a Pydantic Model:** Specify the schema for the data to be extracted and reviewed.
2. **Automated Extraction:** Use LLMs, scrapers, or other tools to extract data from the source.
3. **Request a Review:** Call `review_extraction()` with the source value and extraction result. This creates or fetches a review entry in the database.
4. **Human Review:** Reviewers use Zavod UI to inspect, correct, and accept or reject the extraction.
5. **Use Accepted Data:** If `review.accepted` is true, use `review.extracted_data` in the pipeline. Otherwise, skip or flag for further review.
6. **Assert All Accepted:** Use `assert_all_accepted()` to ensure all required reviews are completed before publishing or exporting data.

### Example (Python)

```python
from zavod.extract.llm import run_typed_text_prompt
from zavod.stateful.review import review_extraction, assert_all_accepted, HtmlSourceValue

class Defendant(BaseModel):
    entity_schema: Literal["Person", "Company", "LegalEntity"]
    name: str

class Defendants(BaseModel):
    defendants: List[Defendant]

def crawl_page(context: Context, url: str, page: _Element) -> None:
    source_value = HtmlSourceValue(
        key_parts=notice_id(url),
        label="Notice of regulatory action taken",
        element=article_element,
        url=url,
    )
    prompt_result = run_typed_text_prompt(
        context,
        prompt=PROMPT,
        string=source_value.value_string,
        response_type=Defendants,
    )
    review = review_extraction(
        context,
        source_value=source_value,
        original_extraction=prompt_result,
        origin=gpt.DEFAULT_MODEL,
    )
    if not review.accepted:
        return
    for item in review.extracted_data.defendants:
        entity = context.make(item.entity_schema)
        entity.id = context.make_id(item.name)
        entity.add("name", item.name, origin=review.origin)
        context.emit(entity)

def crawl(context: Context) -> None:
    for url in urls:
        crawl_page(context, url, page)
    assert_all_accepted(context)
```

## How Zavod UI Implements Data Reviews

- **Review Table:** All review entries are stored in the `review_table` in the database. Each entry includes the source value, extraction result, human-edited data, acceptance status, and metadata.
- **UI Workflow:** Zavod UI presents the source and extraction side-by-side. Reviewers can edit the extraction (YAML/JSON), validate it, and mark it as accepted.
- **Integration:** The ETL pipeline and exporters use only the accepted, human-reviewed data for downstream processing.
- **Re-review Triggers:** If the source data or extraction model changes, or if the data model is updated, reviews can be invalidated and must be redone.

## Best Practices

- **Review Keys:** Use a key that uniquely and consistently identifies the data to be reviewed (e.g., notice ID, unique string from the source).
- **Model Documentation:** Document fields and extraction logic in the Pydantic model. This documentation is surfaced in the UI to guide reviewers.
- **Validation:** Validate user-edited data as early as possible to catch errors before acceptance.

## Summary

Zavod UI is the quality control checkpoint for OpenSanctions data. It ensures that only human-verified, high-quality data is published, especially when dealing with messy, ambiguous, or unstructured sources. The review process is tightly integrated with the ETL pipeline, making it a core part of the data assurance workflow.
