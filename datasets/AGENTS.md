## Crawler Structure

All crawlers defined in `datasets/<country>/<dataset_name>/`

Each crawler must have a `config.yml` and a `crawler.py`. Look at existing datasets for examples. Each crawler must define a `crawl(dataset: Dataset)` function.

When fetching data like JSON, HTML or CSV, use `dataset.fetch_text()`, `dataset.fetch_json()`, `dataset.fetch_html()` with a `cache_days=N` parameter. This ensures we don't overload servers as we develope crawlers.

## Creating entities

For each dataset, you'll want to create multiple [entities](https://followthemoney.tech/explorer/schemata/) (e.g., [Person](https://followthemoney.tech/explorer/schemata/Person/), Company, Organization, Employment, Representation, etc.). You can create an entity with `entity = dataset.make("Person")`.

Each entity has a unique stable ID that you can generate with `entity.id = dataset.make_id('entity', 'name')`. Prefer unique identifiers such as registration numbers, IDs, etc. If there's no unique identifier, use a combination of properties that are unlikely to change (e.g., name + date of birth for a person).

We use the [org-id](https://org-id.guide/about) schema when available, so if you have a company registration number, you can generate the ID with `dataset.make_id(reg_nr=..., register='GB-COH')`.

## Properties

Before creating a new entity type, check [its documentation](https://followthemoney.tech/explorer/schemata/{EntityType}/) to see what properties it has. ALWAYS DO THIS!

You can then add properties like `entity.add('name', 'John Doe')`.

All entries in the `gb` directory will have the property `jurisdiction` set to `gb`. For Scottish datasets, it should be ``gb-sct``.

An important property is `topics`, which is used for categorisation. For example, you might add `entity.add('topics', 'role.lobby')` for lobbyists, `entity.add('topics', 'role.pep')` for politicians, `entity.add('topics', 'gov')` for government departments, etc.

Once you've added all the properties, you can emit the entity with `dataset.emit(entity)`.

Avoid ambiguity at all costs. If you can't be sure about something when creating an entity, crash loudly rather than guessing or falling back to a potentially incorrect value.