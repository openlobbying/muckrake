# FTMQ API: Architecture and Workflow

## Overview

FTMQ API is a FastAPI-based service for exposing FollowTheMoney (FtM) entity data via a read-only HTTP API. It is designed to serve statement-based data stores, supporting filtering, search, and aggregation over entity data. The backend store is adapted from nomenklatura and ftmq, and can be powered by various storage backends (e.g., SQLite, PostgreSQL, or search engines).

## Workflow

1. **Data Storage**
   - FtM entities and statements are stored in a statement-based store, managed by the ftmq library (see `ftmq/store.py`).
   - The store can be backed by a relational database or other supported backends.

2. **API Initialization**
   - The FastAPI app is configured in `ftmq_api/api.py`, with CORS and metadata settings.
   - The store URI and catalog are loaded from configuration (`ftmq_api/settings.py`).

3. **Catalog and Dataset Metadata**
   - The `/catalog` endpoint exposes metadata about available datasets (see `ftmq_api/api.py`).
   - Catalog and dataset objects are loaded and cached (`ftmq_api/store.py`).

4. **Entity Retrieval and Filtering**
   - Endpoints allow retrieval of entities, with filtering by dataset, schema, and property values (`ftmq_api/views.py`, `ftmq_api/query.py`).
   - Query parameters are parsed and validated using Pydantic models.
   - Entities are retrieved from the store, optionally dehydrated or featured (see `retrieve_entities` in `ftmq_api/store.py`).

5. **Search and Aggregation**
   - The API supports full-text search via integration with `ftmq-search` (see `ftmq_api/views.py`).
   - Aggregation endpoints allow for grouped statistics and summaries over entity properties.

6. **Serialization and Response**
   - Responses are serialized using Pydantic models (`ftmq_api/serialize.py`).
   - Entity, aggregation, and error responses are standardized for client consumption.

## Key Features

- **Statement-based model:** Provenance and history are preserved, similar to nomenklatura and Zavod.
- **Flexible backend:** Can use different storage engines, including databases and search backends.
- **Rich filtering:** Filter by dataset, schema, property values, and more.
- **Search integration:** Supports full-text search via external search service.
- **Aggregation:** Group and summarize entity data.
- **Read-only API:** Designed for public data serving, not for data modification.

## Code References

- API setup: `ftmq_api/api.py`
- Store and catalog: `ftmq_api/store.py`
- Query and filtering: `ftmq_api/query.py`
- Views and endpoints: `ftmq_api/views.py`
- Serialization: `ftmq_api/serialize.py`
- Settings: `ftmq_api/settings.py`

## Summary

FTMQ API provides a robust, read-only HTTP interface for FtM entity data, supporting advanced filtering, search, and aggregation. It is suitable for powering public data portals, research tools, and integrations where provenance and flexible querying are required.