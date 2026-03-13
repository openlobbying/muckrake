# Zavod: The OpenSanctions Data Factory

`zavod crawl ./datasets/md/rise_profiles/md_rise_profiles.yml` creates `statements.pack` in the dataset's data directory.

`zavod xref ./datasets/md/rise_profiles/md_rise_profiles.yml` creates deduplication candidates in the `resolver` table in the database.

`zavod dedupe ./datasets/md/rise_profiles/md_rise_profiles.yml` updates the `resolver` table with user decisions.

`zavod dedupe-edges ./datasets/md/rise_profiles/md_rise_profiles.yml` merges edge entities that are effectively duplicates. This should ideally be run automatically.

`zavod load-db ./datasets/md/rise_profiles/md_rise_profiles.yml` loads `statements.pack` into the `statement` table in the database, applying the deduplication decisions from the `resolver` table.




  clear            Delete the data and state paths for a dataset
  <!-- crawl            Crawl a specific dataset -->
  <!-- dedupe           Interactively decide xref candidates -->
  <!-- dedupe-edges     Merge edge entities that are effectively duplicates -->
  dump-file        Dump dataset statements from the archive to a file
  explode-cluster  Destroy a cluster of deduplication matches
  export           Export data from a specific dataset
  <!-- load-db          Load dataset statements from the archive into a database -->
  merge-cluster    Merge multiple entities as duplicates
  publish          Publish data from a specific dataset
  resolver-prune   Remove dedupe candidates from resolver file
  run              Crawl, export and then publish a specific dataset
  summarize        Summarise entities and links in a dataset
  <!-- validate         Check the integrity of a dataset -->
  wd-up            Interactively review and apply wikidata updates from...
  <!-- xref             Generate dedupe candidates from the given dataset -->







Zavod is the core ETL (Extract, Transform, Load) framework used by the OpenSanctions project to build a massive, integrated graph of sanctions targets, politically exposed persons (PEPs), and other entities of interest. It is designed to be reproducible, statement-based, and highly scalable.

## The Journey of a Dataset

The lifecycle of a dataset in Zavod follows a structured path from raw source data to a unified database.

### 1. Metadata Definition (`config.yml`)
Every dataset begins with a YAML metadata file. This file defines:
- **Basics**: Title, summary, and publisher information.
- **Entry Point**: The Python script (usually `crawler.py`) that contains the logic to fetch and parse the data.
- **Prefix**: A short string (e.g., `us-ofac`) used to namespace entity IDs.
- **Lookups**: Data cleaning rules that map messy source values (like "U.S.A." or "United States") to normalized forms (like "us").

### 2. Crawling & Extraction (`crawler.py`)
The crawler is a Python script that uses the `zavod.context.Context` object to interact with the environment.
- **Fetching**: The context provides methods like `fetch_resource()`, `fetch_html()`, and `fetch_json()`. These are preferred over standard `requests` because they provide:
    - **Caching**: Responses are stored in a local cache, keyed by a **fingerprint** (a hash of the URL, method, and request body).
    - **Retries & Timeouts**: Standardized handling of network flakiness.
    - **Resource Tracking**: `fetch_resource()` automatically saves files to the dataset's data directory and tracks them for the final export.
    - **Unblocking**: Integration with services like Zyte API to bypass bot detection.
- **Parsing**: Standard libraries (`csv`, `lxml`, `openpyxl`) or Zavod helpers are used to iterate over the source material.
- **Entity Creation**: The crawler creates entities using `context.make("Person")`.
    - **Under the hood**: This returns a `zavod.entity.Entity` object, which is a subclass of FollowTheMoney's `EntityProxy`. It's essentially a dictionary-like object that validates properties against the FtM schema and automatically associates every value with the current dataset.
- **ID Generation**: Stable IDs are generated using `context.make_id(*parts)`, which hashes the provided strings (e.g., a source-specific ID or a combination of name and birth date) to ensure the same entity gets the same ID in every run.
    - **Deduplication by ID**: If the crawler encounters multiple identical rows and generates the same ID for each, `context.emit()` will produce identical statements. The storage layer (both the `.pack` file and the database) effectively collapses these into a single entity. This is the "first line of defense" against duplicates.
- **Cleaning**: `zavod.helpers` (e.g., `apply_name`, `apply_date`) and the `rigour` library are used to normalize names, dates, and identifiers.
- **Handling Multi-Entity Rows**: If a single row contains multiple entities (e.g., a list of subsidiaries in one cell), the crawler splits the string and iterates:
    - **Splitting**: Use `h.multi_split(value, [";", ","])` to break the string into individual names.
    - **Iteration**: For each name, create a new entity with `context.make()`.
    - **Linking**: Connect the entities using properties (e.g., `company.add("subsidiaries", subsidiary.id)`).
    - **Stable IDs**: Ensure the child entity has a stable ID, often by hashing the parent's ID with the child's name: `context.make_id(company.id, subsidiary_name)`.
- **Emitting**: Once an entity is populated, `context.emit(entity)` sends it to the next stage.

### 3. Statement-Based Storage
Unlike traditional ETLs that overwrite records, Zavod uses a **statement-based model**.
- **Physical Storage**: When an entity is emitted, it is written to a **static file** (usually `statements.pack`) in the dataset's data directory. This is a packed binary format that stores every property of every entity as a discrete statement.
- **Database Loading**: The `zavod load-db` command reads these static files and imports them into a relational database (SQLite or PostgreSQL).
    - **Full Replacement**: For a given dataset, `load-db` **deletes all existing statements** in the database before inserting the new ones from the latest crawl. This ensures the database perfectly reflects the latest state of the source.
- **Original Values**: When data is cleaned, Zavod stores both the **cleaned value** and the **original value**. This ensures that the provenance of the data is never lost.
    - **Example**: If a source lists a birth date as "12 Jan 1980", the crawler might use `h.apply_date(entity, "birthDate", "12 Jan 1980")`.
    - **Storage**: The database will store a statement where `prop` is `birthDate`, `value` is `1980-01-12` (ISO format), and `original_value` is `12 Jan 1980`.
- **Handling Changes**:
    - **Typo Fixes**: If a typo is fixed in the source (e.g., "Johnn" $\rightarrow$ "John"), the crawler will emit a new statement with a new ID. Since the old "Johnn" statement is no longer emitted, it will be removed from the database during the next `load-db` cycle.
    - **No Changes**: If an entity hasn't changed, Zavod uses a persistent **Timestamp Index** to keep the original `first_seen` date, while updating the `last_seen` date to the current run time.
- **Provenance**: This model allows the system to track exactly which source provided which piece of information and when it was last verified.

### 4. Deduplication & Resolution
Once data is in the database, Zavod resolves duplicates across different datasets.
- **Intra-dataset Deduplication**: While `make_id` handles identical records, `zavod xref` can also find duplicates *within* a single dataset if the records are slightly different (e.g., "Boris Johnson" vs "B. Johnson").
- **Cross-Referencing (xref)**: The `zavod xref` command identifies potential duplicates. While it uses the `nomenklatura` library for the heavy lifting, it adds several layers:
    - **Blocking**: It uses "blocking" strategies to avoid comparing every entity with every other entity ($N^2$), focusing only on those with similar names or identifiers.
    - **Custom Logic**: It can apply dataset-specific rules (e.g., "never merge two entities from the same source if they have different national IDs").
- **Resolver**: Judgements (merges or "not a match") are stored in a `resolver.json` file.
- **Canonical IDs**: When two entities are merged, they are assigned a common `canonical_id` (often starting with `NK-` for Nomenklatura). All statements for both entities are now associated with this canonical ID.

### 5. Exporting & Loading
The final stage transforms the raw statements and resolution judgements into usable data products.
- **Views**: A `View` (from `zavod.store`) is a runtime abstraction.
    - **Aggregation**: When you query a `View` for a canonical ID, it doesn't just return one record from the database. Instead, it **aggregates all statements** from all merged entities into a single, unified entity.
    - **Conflict Resolution**: If two sources provide different values for the same property, the `View` resolves this based on dataset priorities or the most recent information.
- **Exporters**: The `zavod export` command runs various exporters to produce:
    - `entities.ftm.json`: The full graph in FollowTheMoney format.
    - `names.txt`: A simple list of all names for search indexing.
    - `targets.nested.json`: A nested JSON format optimized for the OpenSanctions API.
    - `statements.csv`: The raw statement data for advanced users.

## Key Libraries & Tools

| Stage | Libraries Used |
| :--- | :--- |
| **Extraction** | `requests`, `lxml`, `beautifulsoup4`, `openpyxl`, `rigour` |
| **Data Model** | `followthemoney` (FtM) |
| **Normalization** | `normality`, `rigour`, `banal` |
| **Storage** | `SQLAlchemy`, `sqlite3`, `psycopg2` |
| **Deduplication** | `nomenklatura`, `rigour` |
| **CLI / Orchestration** | `click`, `structlog` |

## Summary of the Journey
1. **CSV/XML/Web** $\rightarrow$ `crawler.py` (using `Context` & `Helpers`)
2. `crawler.py` $\rightarrow$ **Statements** (stored in Database)
3. **Statements** + **Resolver Judgements** $\rightarrow$ **Canonical Entities**
4. **Canonical Entities** $\rightarrow$ **Final Exports** (JSON, CSV, API)
