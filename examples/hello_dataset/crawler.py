"""Example crawler: emits a person, two companies and the directorships linking them.

A real crawler fetches its source with ``dataset.fetch_text/json/html`` and maps
each record the same way. Each record here is one unit of work, so a record that
raises is reported and skipped (the run ends ``partial``) instead of aborting
the whole crawl.
"""

from muckrake.dataset import Dataset

COMPANIES = [
    {"number": "00000001", "name": "Acme Widgets Ltd", "director": "Jane Doe"},
    {"number": "00000002", "name": "Acme Holdings Ltd", "director": "Jane Doe"},
]


def crawl_company(dataset: Dataset, record: dict[str, str]) -> None:
    company = dataset.make("Company")
    company.id = dataset.make_id("company", record["number"])
    company.add("name", record["name"])
    company.add("registrationNumber", record["number"])
    dataset.emit(company)

    person = dataset.make("Person")
    person.id = dataset.make_id("person", record["director"])
    person.add("name", record["director"])
    dataset.emit(person)

    directorship = dataset.make("Directorship")
    directorship.id = dataset.make_id("directorship", person.id, company.id)
    directorship.add("director", person.id)
    directorship.add("organization", company.id)
    directorship.add("role", "Director")
    dataset.emit(directorship)


def crawl(dataset: Dataset) -> None:
    for record in COMPANIES:
        dataset.run_unit(record["number"], crawl_company, dataset, record)
