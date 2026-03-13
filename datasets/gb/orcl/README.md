# Office of the Registrar of Consultant Lobbyists (ORCL)

- [ ] Add breaches: [Suspensions of Dannatt and Evans reveal persistent vulnerabilities in Britains' defence-linked Parliamentary lobbying - AOAV](https://aoav.org.uk/2025/suspensions-of-dannatt-and-evans-reveal-persistent-vulnerabilities-in-defence-linked-lobbying/)

The Office of the Registrar of Consultant Lobbyists maintains a [searchable register](https://orcl.my.site.com/CLR_Search) of consultant lobbyists and their clients. This includes details about lobbyists such as addresses and contact details, as well as lists of clients for each quarter. When searching for clients, it shows the hired lobbyist for each quarter.

Implementation details for the Salesforce/AJAX scraper are documented in `datasets/gb/orcl/IMPLEMENTATION_NOTES.md`.

This register excludes [in-house lobbyists](https://publications.parliament.uk/pa/cm201314/cmselect/cmpolcon/601/60103.htm), [foreign lobbyists that don’t have a UK VAT registration](https://www.spotlightcorruption.org/vat-exemption-lobbying-transparency/), the [lobbying of senior civil servants and special advisers](https://publications.parliament.uk/pa/cm201314/cmselect/cmpolcon/601/60103.htm), and [lobbying done over WhatsApp](https://publications.parliament.uk/pa/cm5804/cmselect/cmpubadm/203/summary.html) or other “non-corporate communication channels.”

## Mapping

First, check if a Company Number exists. If it does, create a [`Company`](https://followthemoney.tech/explorer/schemata/Company/) entity for the lobbyist. If there is not Company Number, create a [`LegalEntity`](https://followthemoney.tech/explorer/schemata/LegalEntity/) entity for the lobbyist. Add these properties:

- `name` set to the firm's name.
- `address` set to the firm's address.
- `registrationNumber` set to the firm's company number.
- `topics` set to "role.lobby".

For each client, create an [`Organization`](https://followthemoney.tech/explorer/schemata/Organization/) entity with `name` set to the client's name.

The for each client create a [`Representation`](https://followthemoney.tech/explorer/schemata/Representation/) entity, with:

- `Representation:agent` → the lobbying firm
- `Representation:client` → the client
- `Interest:role` → "Lobbying"
- `Interval:startDate` → the start date of the quarter
- `Interval:endDate` → the end date of the quarter
