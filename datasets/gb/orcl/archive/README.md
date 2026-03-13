# Office of the Registrar of Consultant Lobbyists (ORCL)

https://github.com/data-desk-eco/lobbyharvest/blob/main/lobbyharvest/src/scrapers/uk_orcl.py


The Office of the Registrar of Consultant Lobbyists maintains a [searchable register](https://orcl.my.site.com/CLR_Search) of consultant lobbyists and their clients. This includes details about lobbyists such as addresses and contact details, as well as lists of clients for each quarter. When searching for clients, it shows the hired lobbyist for each quarter.

This register excludes [in-house lobbyists](https://publications.parliament.uk/pa/cm201314/cmselect/cmpolcon/601/60103.htm), [foreign lobbyists that don’t have a UK VAT registration](https://www.spotlightcorruption.org/vat-exemption-lobbying-transparency/), the [lobbying of senior civil servants and special advisers](https://publications.parliament.uk/pa/cm201314/cmselect/cmpolcon/601/60103.htm), and [lobbying done over WhatsApp](https://publications.parliament.uk/pa/cm5804/cmselect/cmpubadm/203/summary.html) or other “non-corporate communication channels.”

## Mapping

There are two columns in the dataset.

We create a [`Organization`](https://followthemoney.tech/explorer/schemata/Organization/) entity for each lobbying firm, with `Thing:name` set to the firm's name.

We also create a [`Organization`](https://followthemoney.tech/explorer/schemata/Organization/) entity for each client, with `Thing:name` set to the client's name.

We link the two with a [`Representation`](https://followthemoney.tech/explorer/schemata/Representation/) entity, with:

- `Representation:agent` → the lobbying firm (`Organization`)
- `Representation:client` → the client (`Organization`)
- `Interest:role` → "Lobbying"
- `Interval:startDate` → the start date of the quarter
- `Interval:endDate` → the end date of the quarter

In addition to the spreadsheets, we will also scrape the [searchable register](https://orcl.my.site.com/clr_search?consultancy) to get contact details and addresses for each lobbying firm, and add those as properties on the `Company` entities.

- `Thing:name` → Name of the lobbying firm
- `Company:registrationNumber` → Company Number (if available)
- `Company:jurisdiction` → "gb"
- `LegalEntity:website`
- `Thing:address` → Address of the lobbying firm
- `Thing:sourceUrl` → URL of the lobbying firm's page on the ORCL register
- `Thing:topics` → https://followthemoney.tech/explorer/types/topic/#:~:text=Lobbyist

We also have lists of directors or partners for each lobbying firm. We will create a `Person` entity for each, with:

- `Thing:name` → Name of the director/partner
- `LegalEntity:directorshipDirector` (if "Director" or "Partner") OR `Person:employers` (otherwise) → link to the `Company` entity for the lobbying firm