# Zavod Data Persistence and Processing

`zavod` is a data ingestion pipeline that produces OpenSanctions-compatible FollowTheMoney datasets. It operates on a "snapshot" model, meaning each successful run generates a complete export of the dataset at that point in time.

## Database Systems Used

Zavod/OpenSanctions uses **multiple database systems** for different purposes:

1. **PostgreSQL** (production): Primary database for stateful data (reviews, positions, programs) and long-term statement storage
2. **SQLite** (development): Default local database for lightweight ETL runs
3. **LevelDB** (via `plyvel`): Fast local dataset-specific "aggregator" for entity assembly during crawls
4. **DuckDB**: Used for performance-intensive analysis and benchmarking

### Database Connection Configuration

- **Environment variable**: `ZAVOD_DATABASE_URI` or `OPENSANCTIONS_DATABASE_URI`
- **Default**: `sqlite:///data/zavod.sqlite3`
- **PostgreSQL detection**: If URI starts with `postgres://`, uses `psycopg2` + SQLAlchemy
- **UI constraint**: The TypeScript UI (`ui/lib/db.ts`) **only supports Postgres** and will throw an error for other database types

### Key Configuration Files

- `zavod/zavod/settings.py`: Database URI configuration (lines 60-62)
- `zavod/zavod/db.py`: SQLAlchemy engine initialization (delegates to nomenklatura)
- `zavod/zavod/stateful/model.py`: SQL schema definitions (statements, positions, reviews, programs)
- `ui/lib/db.ts`: TypeScript UI database connection with schema validation

## Data Storage Architecture

`zavod` uses a combination of local temporary storage and a persistent "Archive" backend (e.g., S3, Google Cloud Storage, or local filesystem) to manage dataset versions.

### 1. Local State (`_state`)
During a crawl, `zavod` maintains a local ephemeral state in the `data/{dataset_name}/_state` directory. This usually includes:
- **LevelDB Store** (via `zavod/zavod/store.py`): Used as a fast, local aggregator for entity assembly during crawls. Statements are written to LevelDB for extremely fast entity deduplication without SQL overhead.
- **Timestamp Index**: Maps `entity_id:statement_id` to `first_seen` timestamps.

### 2. Output Artifacts (`statements.pack`, etc.)
A successful run produces several artifacts in the dataset's directory:
- `statements.pack`: The primary data output containing all FollowTheMoney statements for the dataset.
- `index.json`: Metadata about the dataset resources.
- `issues.json`: Log of warnings and errors.
- `entities.delta.json`: A record of changes since the last version.

### 3. The Archive
The **backend archive** is the source of truth for long-term storage. It stores artifacts for every version (timestamped) of the dataset. `zavod` pushes new versions to the archive and can retrieve previous versions to calculate diffs or backfill timestamps.

### 4. SQL Database (SQLite/PostgreSQL)

Zavod maintains a **stateful SQL database** for:
- **Statements table**: Long-term storage of FollowTheMoney statements (created by `nomenklatura.db.make_statement_table()`)
- **Resolver table**: Entity deduplication/merge decisions
- **Position table**: PEP (Politically Exposed Person) data with soft deletes (`deleted_at`)
- **Review table**: Manual data verification/acceptance tracking
- **Program table**: Sanctions programs metadata

**Schema Design Principles:**
- Uses `JSON` columns for arrays/objects (works in both SQLite and Postgres)
- "Soft delete" pattern with `deleted_at` timestamps
- Audit fields: `modified_at`, `modified_by`, `created_at`
- Schema migrations via manual SQL files in `zavod/migrations/` (Postgres-specific syntax)

**Connection Pooling:**
- Python backend: Standard SQLAlchemy pooling
- TypeScript UI: `pg.Pool` with max 10 connections

---

## How Updates Are Processed

Since `zavod` reconstructs the dataset from scratch on every run (usually), "updates" are essentially differences between the newly generated snapshot and the previous one.

### 1. New Records
*   **Action**: The crawler emits new entities/statements.
*   **Result**: They appear in `statements.pack`.
*   **Timestamps**: `first_seen` is set to the current run time.
*   **Delta**: Marked as `ADD` in `entities.delta.json`.

### 2. Unchanged Records
*   **Action**: The crawler emits the same entities/statements as before.
*   **Result**: They appear in `statements.pack`.
*   **Timestamps**: `zavod` checks its `TimestampIndex` (preloaded from the previous archived version). If the statement ID matches, the original `first_seen` date is preserved. `last_seen` is updated to the current time.
*   **Delta**: Not included in `entities.delta.json`.

### 3. Changed Records (Updates)
*   **Action**: A record in the source has changed (e.g., a person's address changed).
*   **Result**:
    *   The old statements (with the old address) are **not emitted**. They are effectively deleted from the current snapshot.
    *   New statements (with the new address) are emitted.
    *   **Entity Level**: The *Entity* persists (same ID), but its hash changes.
*   **Delta**: Marked as `MOD` (Modified) in `entities.delta.json`.

### 4. Deleted Records (Removed from Source)
*   **Action**: A record is no longer present in the source.
*   **Result**: It is simply **absent** from `statements.pack` in the new version.
*   **Delta**: Marked as `DEL` in `entities.delta.json`.

---

## Failure Modes

### Inaccessible Source
If a crawler crashes or fails (e.g., network error, parser error):
1.  The `zavod` runner catches the exception.
2.  It calls `publish_failure`.
3.  **No Data Published**: The `statements.pack` file is deleted to prevent partial/corrupt data from being released.
4.  **Metadata Updated**: A new `index.json` is published, but it will lack the data resources (statements). This effectively signals that the "latest" version is broken or empty.
5.  **History Preserved**: Previous successful versions remain in the archive and can still be accessed, though `latest` points to the failed run's metadata.

---

## Summary Table

| Scenario | `statements.pack` | `first_seen` | `entities.delta.json` |
| :--- | :--- | :--- | :--- |
| **New Record** | Present | Now | `ADD` |
| **Unchanged** | Present | Original Date | *(Absent)* |
| **Changed** | New values only | Now (for new props) | `MOD` |
| **Deleted** | Absent | N/A | `DEL` |
| **Crawl Fail** | **File missing** | N/A | N/A |

## Artifact Usage & State Reconstruction

This pipeline does not "update" a database in place. Instead, it maintains continuity between full snapshots using specific artifacts. Here is how each output file is utilized:

### Critical for State Continuity
These files are fetched from the archive (previous version) to inform the current run:
*   **`statements.pack`**: Used to build the `TimeStampIndex`.
    *   *Mechanism*: Zavod streams the statements from the *previous* successful run. If an emitted statement ID matches one from the past, the original `first_seen` timestamp is copied over. This is how the system remembers when a record first appeared, irrelevant of the fact that the database was just wiped and rebuilt.
*   **`entities.hash`**: Used to calculate Deltas (`entities.delta.json`).
    *   *Mechanism*: Stores a hash of every entity's properties from the previous run. The current run compares its new entity hashes against these to determine if an entity was `MOD` (Modified), `ADD`, or `DEL`.
*   **`versions.json`**: The registry of history.
    *   *Mechanism*: Used to locate the "latest" previous version ID to know which artifacts to backfill.

### Consumption Artifacts
These are strictly outputs for downstream systems (like Nomenklatura or user analysis) and are not read back by Zavod:
*   **`index.json`**: The entry point for consumers. It tells systems where to find the data and what the dataset metadata is.
*   **`issues.json`**: Error logs for human review or monitoring alerts.
*   **`entities.delta.json`**: Used by downstream systems to process incremental updates (e.g., sending alerts for new sanctions) without re-ingesting the whole dataset.

---

## Architectural Analysis: Evaluation & Critique

### Advantages
1.  **Immutability & Auditability**: Each run produces a frozen artifact that will never change. This is critical for the domain of sanctions and PEPs (Politically Exposed Persons), where you might need to prove *exactly* what data was available on a specific date.
2.  **"Clean Slate" Reliability**: Because the database is destroyed and rebuilt every time, there is zero risk of "zombie data" (records that were deleted from the source but stuck in your local DB because a delete command was missed). If it's not in the source *now*, it won't be in the snapshot.
3.  **Schema Evolution**: You can change the data model or parsing logic radically. The next run simply re-interprets the entire source with the new logic. You don't need complex migration scripts to update millions of existing rows.
4.  **Stateless Crawlers**: The crawlers (scrapers) themselves can be very dumb. They don't need to check "does this exist?". They just emit what they see.

### Disadvantages
1.  **High Latency**: You cannot have "real-time" updates. If a record changes 1 second after a crawl starts, it won't be seen until the *next* crawl cycle completes.
2.  **Resource Intensive**: Processing the *entire* dataset for every single update is redundant. If you have 10 million records and 1 changes, you still scrape and serialize 10 million records.
3.  **Storage Scale**: Storing full snapshots for every version consumes massive amounts of space compared to a mutable database with a transaction log.

### Is there a better way?
For **this specific use case** (aggregating public data sources for compliance), the Snapshot/Backfill model is likely **optimal**.

*   *Why not a mutable database?* Public sources (HTML, CSVs, PDFs) rarely provide "diffs" or "change logs". They just give you the current state. To find deletes in a mutable DB, you'd still have to scrape everything to check what's missing. You would gain little efficiency but lose the "clean slate" guarantee.
*   *Why not Event Sourcing?* Managing an append-only log of 500+ heterogeneous scrapers is an operational nightmare. If a scraper has a bug and emits bad events, "undoing" that in an event stream is painful. In Zavod, you just fix the bug and re-run.

**Verdict**: While it looks inefficient strictly from a CPU/IO perspective, it is the most robust way to ensure **correctness** when dealing with low-quality, untrusted external data sources.

---

## Proposed Workflow for Muckrake

The `muckrake` framework currently uses a hybrid approach: crawlers output snapshots (`statements.jsonl`), but the loader blindly inserts them into a persistent SQLite database. This creates a risk of "zombie data" (records deleted from source remain in DB).

To adopt the robust OpenSanctions/Zavod philosophy while keeping `muckrake` simple (since it lacks an "Archive" backend), the following workflow is recommended:

### 1. Robust Snapshot Crawling with Persistence
Unlike Zavod which uses complex LevelDB indexing, Muckrake can use the **previous snapshot file** as its state.

*   **Before Crawl**: Check if `data/datasets/{name}/statements.jsonl` exists.
    *   If yes, read it into memory (streaming).
    *   Build a map: `id_to_first_seen = {stmt.id: stmt.first_seen}`.
*   **During Crawl**:
    *   Crawler generates entities. `Dataset.make_id` ensures stable IDs.
    *   On `emit(entity)`:
        *   For each statement, check if `stmt.id` is in `id_to_first_seen`.
        *   **Match**: Set `stmt.first_seen = old_timestamp`.
        *   **No Match**: Set `stmt.first_seen = now`.
*   **After Crawl**:
    *   The new `statements.jsonl` overwrites the old one. It is now the complete, clean state of the world.

### 2. Atomic Database Loading
The `load` command must ensure the database perfectly reflects the snapshot.
### 3. Resolver Judgement Persistence
The manual work of deduplication (stored in the SQLite `xref` and `canonical` tables) is valuable and must be decoupled from the ephemeral database state.

*   **Problem**: If the SQLite DB is corrupted or deleted, judgements are lost.
*   **Solution**: Source-control the judgements.
*   **New Command**: `muckrake save-judgements`
    *   Dumps the `resolver` state to `data/judgements.json` (sorted, pretty-printed).
    *   This file should be committed to Git.
*   **New Command**: `muckrake load-judgements`
    *   Reads `data/judgements.json` and repopulates the resolver tables.
    *   This makes the workflow: `git pull` -> `load-judgements` -> `load` (statements).

### Architecture Note: Why DB + JSON?
**Q: "Doesn't Nomenklatura use DuckDB for deduplication anyway?"**

Yes, but for a specific purpose.
*   **DuckDB (The Index)**: Nomenklatura builds a *temporary* DuckDB index from your data to perform the "blocking" phase (finding candidates that look similar). This index is ephemeral; it is rebuilt on demand and destroyed when the process ends. It does *not* store your decisions.
*   **SQLite/Postgres (The Store)**: Your human decisions ("Entity A is Entity B") are stored in the *Resolver* tables in your primary database (SQLite in `muckrake`). This is the authoritative state of the graph.
*   **JSON (The Backup)**: Since SQLite files are binary and hard to version control, we export the decisions to `judgements.json` to keep a text-based history in Git.

*   **Current State**: `INSERT INTO statement ...` (Accumulates data).
*   **New State**:
    *   Start Transaction.
    *   `DELETE FROM statement WHERE dataset = :dataset_name`
    *   `INSERT INTO statement ...` (from new `statements.jsonl`).
    *   Commit.
    *   *Result*: Any record dropped from the source is immediately dropped from the DB.

### 3. Resolver Judgement Persistence
The manual work of deduplication (stored in the SQLite `xref` and `canonical` tables) is valuable and must be decoupled from the ephemeral database state.

*   **Problem**: If the SQLite DB is corrupted or deleted, judgements are lost.
*   **Solution**: Source-control the judgements.
*   **New Command**: `muckrake save-judgements`
    *   Dumps the `resolver` state to `data/judgements.json` (sorted, pretty-printed).
    *   This file should be committed to Git.
*   **New Command**: `muckrake load-judgements`
    *   Reads `data/judgements.json` and repopulates the resolver tables.
    *   This makes the workflow: `git pull` -> `load-judgements` -> `load` (statements).

### Architecture Note: Why DB + JSON?
*   **Why not just JSON?** Deduplication requires complex graph queries (finding connected components, calculating transitivity) which are extremely slow and memory-intensive on raw JSON files. A SQL database (SQLite/Postgres) provides the necessary indexing for interactive performance.
*   **Why JSON export?** Databases are binary blobs that don't mix well with Git. Exporting to sorted JSON allows you to version-control your decisions ("Who merged this company? When?"). This mirrors the OpenSanctions model: **Active State in DB** (for speed) <-> **Persistent State in JSON** (for history).
