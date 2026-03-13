# Donations

The UK Electoral Commission maintains a [searchable database of political donations](https://search.electoralcommission.org.uk/), including the donors and recipients. This is easily scrapeable.

## To-do

- [ ] Incorporate [these deduplications](https://donation.watch/en/unitedkingdom/transparency#sec-aggregated-donors)

## Mapping

Donations can go to political parties, individual politicians, or campaign groups.

Regardless of the type, we have the following properties:

- `Thing:name` → `RegulatedEntityName`
- `LegalEntity:jurisdiction` → if `RegisterName` is "Great Britain", then "gb", if Northern Ireland, then "gb-nir"

If they're a person (determined by `RegulatedEntityType`), we create a `Person` entity, with:

- `Person:position` → `RegulatedDoneeType`

If they're an organisation, we create an [`Organization`](https://followthemoney.tech/explorer/schemata/Organization/) entity, with:

- `LegalEntity:legalForm` → `RegulatedDoneeType`

If they're a political party, we can also add:

- `LegalEntity:legalForm` → `RegulatedEntityType`

The donor can be either a Person or an Organization (determined by `DonorStatus`).

Regardless of type, we create an entity, with:

- `Thing:name` → `DonorName`
- `Thing:address` → `Postcode`
- `LegalEntity:jurisdiction` → if `RegisterName` is "Great Britain", then "gb", if Northern Ireland, then "gb-nir"

If it's a company:

- `Company:registrationNumber` → `CompanyRegistrationNumber`


The donation

- `Value:amount` → `Value`
- `Value:currency` → "GBP"
- `Payment:payer` → link to the donor entity
- `Payment:beneficiary` → link to the recipient entity
- `Interval:date` → `ReceivedDate` (or `AcceptedDate`, `ReportedDate`)
- `Interval:summary` → "Donation"
- `Payment:purpose` → `DonationType`, `NatureOfDonation`, `PurposeOfVisit`, `DonationAction`, `CampaigningName`
- `Interval:recordId` → `ECRef`
- `Interval:sourceUrl` → `https://search.electoralcommission.org.uk/English/Donations/{ECRef}`