---
name: followthemoney-code-writer
description: Documentation for the Follow The Money (FTM) Framework. You MUST use this skill whenever you deal with any code, configuration, or documentation related to the FTM framework (including `followthemoney`, `nomenklatura`, `zavod`).
---

# Follow The Money

[FollowTheMoney](https://followthemoney.tech/) (FtM) is a data model for financial crime investigations and document forensics.

Mappings are a mechanism for generating entities from structured data sources, including tabular data and SQL databases. Mappings are defined in YAML files that describe how information from a table can be projected to FollowTheMoney entities.

These are some (but not all) of the schemata:
- Name
- Asset
- Associate
- Company
- Directorship
- Employment
- Event
- Family
- LegalEntity
- Membership
- Occupancy
- Organization
- UnknownLink
- Ownership
- Payment
- Person
- Position
- PublicBody
- Representation
- Succession

Each schema has a set of properties, which can be accessed like https://followthemoney.tech/explorer/schemata/Person/ . When you create a new entity, you MUST consult the schema to ensure you are using the correct properties.