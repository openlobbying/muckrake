# Foreign Influence Registration Scheme (FIRS)

The UK requires "the registration of arrangements to carry out political influence activities in the UK at the direction of a foreign power". [The register](https://foreign-influence-registration-scheme.service.gov.uk/public-register) is quite thin now, but it's fairly new, so it could be expanded in the future.

## Mapping

We create a [`Organization`](https://followthemoney.tech/explorer/schemata/Organization/) (or `Company`) entity for each lobbying firm. In either case, we map:

- `Thing:name` → Registrant / Name
- `Thing:previousName` → Registrant / Previous names
- `Thing:country` → Registrant / Country or territory of incorporation or main office
- `Company:registrationNumber` → Registrant / Company registration number (this determines we use `Company` instead of `Organization` when present)
- `Thing:address` → Registrant / Registered or main address
- `Thing:topics` → "role.lobby"

For [at least one entry in the register](https://foreign-influence-registration-scheme.service.gov.uk/article/1200/Walk-Through-Walls-OTTG-Ltd), there is an additional "Organisations involved" section, which could be mapped as additional `Organization`:

- `Thing:name` → Organisations involved / Name
- `Thing:topics` → "role.lobby"

For each client, we create a [`PublicBody`](https://followthemoney.tech/explorer/schemata/PublicBody/) entity:

- `Thing:name` → Arrangement / Name of foreign power
- `Thing:country` → Arrangement / Country or territory of foreign power
- `Thing:summary` → Arrangement / Type of foreign power
- `Thing:topics` → "gov"

Then, we link them with a [`Representation`](https://followthemoney.tech/explorer/schemata/Representation/) entity, with:

- `Representation:agent` → the lobbying firm (`Company` or `Organization`)
- `Representation:client` → the foreign power (`PublicBody`)
- `Interest:role` → "Lobbying"
- `Interval:summary` → Activity overview
- `Interval:startDate` → Activity overview or Activity details / Start date
- `Interval:endDate` → Activity overview or Activity details  / End date (if present)

If there is an "Organisations involved" section, create an additional `Representation` entity between this other organisation and the foreign power, with the same properties as above.

For all entities, we also map:
- `Thing:sourceUrl` → Current URL for the registration