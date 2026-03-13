# ETL Frameworks Analysis: Zavod vs. Investigraph

This document provides a thorough analysis and comparison of **Zavod** and **Investigraph**, two powerful ETL frameworks designed for creating [Follow the Money (FtM)](https://followthemoney.tech/) entities.

## Overview

| Feature | Zavod | Investigraph |
| :--- | :--- | :--- |
| **Primary Philosophy** | Imperative (Python-first) | Declarative (YAML-first) |
| **Orchestration** | Custom runner / CLI | [Prefect.io](https://prefect.io/) |
| **Data Handling** | Manual parsing (e.g., `csv.DictReader`) | [Pandas](https://pandas.pydata.org/) based |
| **Mapping Logic** | Python code (`entity.add()`) | YAML configuration (`queries`) |
| **Target Use Case** | Complex, heterogeneous sources (Sanctions, PEPs) | Standardized tabular datasets (CSV, Excel) |

---

## 1. Source Dataset Definition

Both tools use YAML for metadata, but their scope differs significantly.

### Zavod
In Zavod, the YAML file is primarily for **metadata and entry points**. It describes *what* the dataset is, but not *how* to process it.
- **Metadata**: Name, title, summary, publisher info, and data URLs.
- **Entry Point**: Explicitly points to a Python script (e.g., `entry_point: crawler.py`).
- **Example**:
  ```yaml
  name: uk_gov_meetings
  prefix: gb-gov-meetings
  entry_point: crawler.py
  data:
    url: "https://example.com/data.csv"
  ```

### Investigraph
In Investigraph, the YAML file is a **complete pipeline specification**. It defines the extraction, transformation, and loading logic.
- **Metadata**: Similar to Zavod (name, title, publisher).
- **Pipeline**: Includes `extract`, `transform`, and `load` blocks.
- **Example**:
  ```yaml
  extract:
    sources:
      - uri: https://example.com/data.csv
        pandas:
          read:
            options: { encoding: utf-8 }
  transform:
    queries:
      - entities:
          org:
            schema: Organization
            keys: [Id]
  ```

---

## 2. Crawling and Scraping

### Zavod (Imperative)
Crawling in Zavod is done manually within the `crawl(context)` function of the Python script.
- **Fetching**: Uses `context.fetch_resource()` to download files.
- **Parsing**: The developer chooses the library (e.g., `csv`, `lxml`, `json`).
- **Flexibility**: Since it's pure Python, it can handle complex multi-step scraping, authentication, and API pagination easily.
- **Helpers**: Provides `zavod.helpers` for common tasks like date normalization and name splitting.

### Investigraph (Declarative)
Investigraph automates the extraction of common formats via its `extract` block.
- **Pandas Integration**: It leverages Pandas to read CSV, Excel, and other tabular formats directly into DataFrames.
- **Low Code**: For most CSV/Excel sources, no Python code is required for extraction.
- **Customization**: Allows "hooking" into the pipeline with custom Python functions if the declarative approach is insufficient.

---

## 3. Creating Follow the Money Entities

### Zavod (Manual Mapping)
Entities are created and emitted one by one in Python.
- **Creation**: `entity = context.make("Person")`
- **ID Generation**: Uses `context.make_slug()` or `context.make_id()` for deterministic IDs.
- **Properties**: `entity.add("name", row.get("Name"))`
- **Emission**: `context.emit(entity)`
- **Logic**: Allows complex conditional logic (e.g., "if column X is Y, create a Relationship entity").

### Investigraph (Declarative Mapping)
Entities are mapped using a query-like syntax in the `transform` block of the YAML.
- **Schema Mapping**: Defines which FtM schema to use for a set of records.
- **Property Mapping**: Maps FtM properties directly to source columns.
  ```yaml
  properties:
    name:
      column: Name
    website:
      column: Website
  ```
- **ID Generation**: Defined via `keys` (columns used to hash the ID) and `key_literal`.
- **Efficiency**: Highly efficient for 1:1 or 1:N mappings from tabular data.

---

## Summary of Differences

| Aspect | Zavod | Investigraph |
| :--- | :--- | :--- |
| **Learning Curve** | Requires Python proficiency. | Easier for non-coders (YAML-based). |
| **Maintenance** | Higher (code-heavy). | Lower (config-heavy). |
| **Data Cleaning** | Done via Python logic and helpers. | Done via Pandas options or custom hooks. |
| **ID Strategy** | Explicitly managed in code. | Implicitly managed via `keys` in YAML. |
| **Ecosystem** | Part of the OpenSanctions toolchain. | Independent framework, often used with `ftmq`. |

**Conclusion**: Use **Zavod** when dealing with messy, non-tabular data or sources requiring complex scraping logic. Use **Investigraph** for rapid onboarding of structured tabular datasets where a declarative mapping is sufficient.