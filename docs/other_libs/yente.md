## Architectural Notes and Workflow

Yente is designed to serve entity data for search and matching via a high-performance API. The workflow and architectural choices are as follows:

### Workflow Overview

1. **Data Extraction & ETL:**
	- Dataset crawlers (in Zavod) process raw source data into FollowTheMoney (FtM) entities and emit statements.
	- Statements are loaded into a relational database (SQLite/PostgreSQL) for provenance, deduplication, and complex modeling.

2. **Export for Serving:**
	- Entities are exported from the database as line-delimited JSON (JSONL), providing a denormalized, entity-centric snapshot.

3. **Indexing for Search:**
	- Yente loads the JSONL entities and indexes them into a search backend (Elasticsearch or OpenSearch).

4. **API Serving:**
	- The Yente API serves entity data from the search engine, optimized for fast search, filtering, and retrieval.
	- The public website (opensanctions.org) fetches entity data from the Yente API, not directly from the database.

### Why Not Serve Directly from the Database?

- **Search engines** (Elasticsearch/OpenSearch) are optimized for fast, scalable search and filtering, not for complex joins or provenance.
- **Denormalized data** in JSONL is easier to bulk load and index for search.
- **Separation of concerns:** The ETL/database handles provenance and modeling; the search engine handles fast API queries.
- **Portability:** JSONL exports are easy to distribute, version, and stream.
- **Security:** The database is not exposed to the public API, reducing risk.

### When to Use a Database Directly

- If you need complex joins, provenance, or transactional integrity, serve from a database.
- For public-facing search and entity lookup, a search engine is usually much faster and more scalable.

### Summary

Yente's architecture is designed for speed and scalability in search and API serving. The ETL/database layer is still essential for data modeling and provenance, but the public API and website use the search engine for performance.

## Data Loading and Serving in Yente

Yente is designed to ingest entity data from a variety of sources, including remote URLs, local files, and databases such as SQLite. The core logic for data loading is asynchronous and optimized for large, line-delimited JSON datasets, but can be adapted to other formats, including database backends.

### Loading Data from a Database (e.g., SQLite)

While Yente's default loaders (`yente/data/loader.py`) are built for HTTP and file-based sources, the architecture allows for loading from a database like SQLite by implementing a compatible async generator that yields entity records as dictionaries. For SQLite, this typically involves:

- Opening a connection to the SQLite database (using an async library such as `aiosqlite`).
- Executing a query to fetch entity records.
- Iterating over the result set and yielding each row as a dictionary (matching the FollowTheMoney entity schema).

This generator can then be plugged into the indexing and serving pipeline in place of the standard file/HTTP loaders.

**Example (conceptual):**

```python
import aiosqlite
from typing import AsyncGenerator, Dict, Any

async def load_entities_from_sqlite(db_path: str) -> AsyncGenerator[Dict[str, Any], None]:
	async with aiosqlite.connect(db_path) as db:
		async with db.execute("SELECT * FROM entities") as cursor:
			async for row in cursor:
				yield dict(row)
```

This loader can be used in place of `load_json_lines` in the `DatasetUpdater` logic.

### Serving Data via the API

Once entities are loaded (from SQLite or any other source), they are passed through the indexing pipeline and made available via the API endpoints. The API is built with FastAPI and serves entity data as JSON, using Pydantic models for serialization and validation.

The typical flow is:

1. **Data is loaded from the source (e.g., SQLite) as entity dictionaries.**
2. **Entities are indexed or cached as needed.**
3. **API endpoints (e.g., `/search`, `/entity/{id}`) return entities as JSON responses.**

This modular approach allows Yente to support a wide range of data sources, including direct database connections, with minimal changes to the core serving logic.
