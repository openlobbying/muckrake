import re
from typing import Dict, Optional, Any

from muckrake.util import parse_date
from ..util import make_mp, make_legal_entity


# Cache for parent interests: {interest_id: (fields_data, employer_entity)}
PARENT_CACHE: Dict[int, tuple] = {}


def get_payment_date(
    item: Dict[str, Any], fields_data: Dict[str, Any]
) -> Optional[str]:
    for field_name in ("ReceivedDate", "AcceptedDate", "StartDate"):
        value = fields_data.get(field_name)
        if value:
            return parse_date(value)
    registration_date = item.get("registrationDate")
    if registration_date:
        return parse_date(registration_date)
    return None


def add_member_source_url(payment, item: Dict[str, Any]) -> None:
    member_id = item.get("member", {}).get("id")
    if member_id:
        payment.add(
            "sourceUrl",
            f"https://members.parliament.uk/member/{member_id}/registeredinterests",
        )


def classify_support_programme(
    item: Dict[str, Any], fields_data: Dict[str, Any]
) -> Optional[str]:
    combined_text = " ".join(
        filter(
            None,
            [
                item.get("summary"),
                fields_data.get("DonationSource"),
                fields_data.get("PaymentDescription"),
            ],
        )
    ).lower()
    if "loan" in combined_text:
        return "Loan"
    if fields_data.get("DonationSource") or fields_data.get("DonorName"):
        return "Donation"
    return None


def build_support_description(fields_data: Dict[str, Any]) -> Optional[str]:
    desc_parts = []
    payment_description = fields_data.get("PaymentDescription")
    if payment_description:
        desc_parts.append(payment_description)

    labels = {
        "DonationSource": "Source",
        "PaymentType": "Type",
        "DonorStatus": "Donor status",
        "IsSoleBeneficiary": "Sole beneficiary",
        "DonorTrustDetails": "Trust details",
        "DonorOtherDetails": "Other donor details",
    }
    for field, label in labels.items():
        value = fields_data.get(field)
        if value is not None and value != "":
            desc_parts.append(f"{label}: {value}")

    if desc_parts:
        return "\n".join(desc_parts)
    return None


def get_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the list of fields from the API interest object into a dictionary."""
    fields_data = {}
    for field in item.get("fields", []):
        name = field.get("name")
        value = field.get("value")
        if name:
            fields_data[name] = value
    return fields_data


def get_currency(item: Dict[str, Any], field_name: str) -> Optional[str]:
    """Extract currency code from a field's typeInfo."""
    for field in item.get("fields", []):
        if field.get("name") == field_name:
            return field.get("typeInfo", {}).get("currencyCode")
    return None


def fetch_interest(dataset, interest_id: int) -> Optional[Dict[str, Any]]:
    """Fetch details for a single interest by its ID."""
    url = f"https://interests-api.parliament.uk/api/v1/Interests/{interest_id}"
    return dataset.fetch_json(url, cache_days=7)


def process_employment(dataset, item: Dict[str, Any], member):
    """Process Category 12 (Employment and earnings) - creates Employment relationship."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Determine the correct schema for the employer
    employer_schema = "LegalEntity"
    if fields_data.get("IsPaidAsDirectorOfPayer"):
        employer_schema = "Organization"
    elif fields_data.get("PayerIsPrivateIndividual"):
        employer_schema = "Person"

    payer_name = fields_data.get("PayerName")
    employer = make_legal_entity(
        dataset,
        name=payer_name,
        address=fields_data.get("PayerPublicAddress"),
        summary=fields_data.get("PayerNatureOfBusiness"),
        schema=employer_schema,
    )

    if not employer:
        dataset.log.warning(f"No employer name for employment {item_id}")
        return fields_data, None

    # Create the Employment relationship
    employment = dataset.make("Employment")
    employment.id = dataset.make_id("employment", item_id)
    employment.add("role", fields_data.get("JobTitle"))
    employment.add("employer", employer)
    employment.add("employee", member)

    start_date = fields_data.get("StartDate")
    if start_date:
        employment.add("startDate", parse_date(start_date))
    end_date = fields_data.get("EndDate")
    if end_date:
        employment.add("endDate", parse_date(end_date))

    dataset.emit(employment)

    # If director, create a Directorship too
    if fields_data.get("IsPaidAsDirectorOfPayer"):
        directorship = dataset.make("Directorship")
        directorship.id = dataset.make_id("directorship", member.id, employer.id)
        directorship.add("director", member)
        directorship.add("organization", employer)

        if start_date:
            directorship.add("startDate", parse_date(start_date))
        if end_date:
            directorship.add("endDate", parse_date(end_date))

        dataset.emit(directorship)

    return fields_data, employer


def process_payment(dataset, item: Dict[str, Any], member, parent_employer=None):
    """Process Categories 1 & 2 (Employment payments) - creates Payment."""
    item_id = item.get("id")
    fields_data = get_fields(item)
    item_summary = item.get("summary")

    payment = dataset.make("Donation")
    payment.id = dataset.make_id("payment", item_id)

    amount = fields_data.get("Value")
    if amount:
        payment.add("amount", amount)
        currency = get_currency(item, "Value")
        if currency:
            payment.add("currency", currency)

    payment.add("beneficiary", member)

    date = get_payment_date(item, fields_data)
    if date:
        payment.add("date", date)

    purpose = fields_data.get("JobTitle")
    if purpose:
        payment.add("purpose", purpose)

    payment.add("summary", item_summary)

    # Add the parent employer as a payer if available
    if parent_employer:
        payment.add("payer", parent_employer)

    # If there's an ultimate payer, create it and add it as an additional payer
    if fields_data.get("IsUltimatePayerDifferent"):
        ultimate_name = fields_data.get("UltimatePayerName")
        if ultimate_name:
            ultimate_payer = make_legal_entity(
                dataset,
                name=ultimate_name,
                address=fields_data.get("UltimatePayerAddress"),
                summary=fields_data.get("UltimatePayerNatureOfBusiness"),
            )
            if ultimate_payer:
                payment.add("payer", ultimate_payer)

    # Build description from various hour/period fields
    desc_parts = []
    labels = {
        "RegularityOfPayment": "Regularity",
        "PeriodForHoursWorked": "Period",
        "PaymentDescription": "Description",
        "HoursWorked": "Hours",
        "HoursDetails": "Details",
    }
    for field, label in labels.items():
        val = fields_data.get(field)
        if val:
            desc_parts.append(f"{label}: {val}")
    if desc_parts:
        payment.add("description", "\n".join(desc_parts))

    add_member_source_url(payment, item)

    dataset.emit(payment)


def process_donation(dataset, item: Dict[str, Any], member):
    """Process Category 3 (Donations and other support) - creates Payment."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    payment = dataset.make("Gift")
    payment.id = dataset.make_id("donation", item_id)
    payment.add("beneficiary", member)

    # Donor - check for company registration number
    donor_name = fields_data.get("DonorName")
    if donor_name:
        # Extract company registration details if available
        reg_nr = fields_data.get("DonorCompanyIdentifier")
        register = None
        if (
            reg_nr
            and fields_data.get("DonorCompanyIdentifierSource") == "Companies House"
        ):
            register = "GB-COH"

        # Determine schema based on donor type
        donor_type = fields_data.get("DonorType")
        schema = "LegalEntity"
        if donor_type == "Company":
            schema = "Organization"
        elif donor_type == "Individual":
            schema = "Person"

        donor = make_legal_entity(
            dataset,
            name=donor_name,
            address=fields_data.get("DonorPublicAddress"),
            summary=fields_data.get("DonorNatureOfBusiness"),
            schema=schema,
            reg_nr=reg_nr,
            register=register,
        )
        if donor:
            payment.add("payer", donor)

    # Amount
    amount = fields_data.get("Value")
    if amount:
        payment.add("amount", amount)
        currency = get_currency(item, "Value")
        if currency:
            payment.add("currency", currency)

    # Dates
    date = get_payment_date(item, fields_data)
    if date:
        payment.add("date", date)

    # Dates over interval
    received_end_date = fields_data.get("ReceivedEndDate")
    if received_end_date:
        payment.add("endDate", parse_date(received_end_date))

    # Classification and narrative fields
    programme = classify_support_programme(item, fields_data)
    if programme:
        payment.add("programme", programme)

    payment.add("purpose", fields_data.get("PaymentDescription"))
    payment.add("summary", item.get("summary"))
    payment.add("recordId", str(item_id))

    description = build_support_description(fields_data)
    if description:
        payment.add("description", description)

    add_member_source_url(payment, item)

    dataset.emit(payment)


def process_gift_uk(dataset, item: Dict[str, Any], member):
    """Process Category 4 (Gifts from UK sources) - creates Payment (in-kind)."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    payment = dataset.make("Gift")
    payment.id = dataset.make_id("gift_uk", item_id)
    payment.add("beneficiary", member)

    # Donor - check for company registration number
    donor_name = fields_data.get("DonorName")
    if donor_name:
        # Extract company registration details if available
        reg_nr = fields_data.get("DonorCompanyIdentifier")
        register = None
        if (
            reg_nr
            and fields_data.get("DonorCompanyIdentifierSource") == "Companies House"
        ):
            register = "GB-COH"

        # Determine schema based on donor type
        donor_type = fields_data.get("DonorType")
        schema = "LegalEntity"
        if donor_type == "Company":
            schema = "Organization"
        elif donor_type == "Individual":
            schema = "Person"

        donor = make_legal_entity(
            dataset,
            name=donor_name,
            address=fields_data.get("DonorPublicAddress"),
            summary=fields_data.get("DonorNatureOfBusiness"),
            schema=schema,
            reg_nr=reg_nr,
            register=register,
        )
        if donor:
            payment.add("payer", donor)

    # Amount
    amount = fields_data.get("Value")
    if amount:
        payment.add("amount", amount)
        currency = get_currency(item, "Value")
        if currency:
            payment.add("currency", currency)

    # Dates
    date = get_payment_date(item, fields_data)
    if date:
        payment.add("date", date)

    # Description
    payment.add("purpose", fields_data.get("PaymentDescription"))
    payment.add("summary", item.get("summary"))

    # APPG context
    if fields_data.get("Appg"):
        payment.add("description", f"APPG: {fields_data.get('Appg')}")

    add_member_source_url(payment, item)

    dataset.emit(payment)


def extract_company_number(name: str) -> tuple[Optional[str], Optional[str], str]:
    """Extract company number from name like 'Company Name (Company No. 12345678)'.

    Returns: (reg_nr, register, cleaned_name)
    """
    company_match = re.search(r"\(Company No\.\s*(\d+)\)", name)
    if company_match:
        reg_nr = company_match.group(1)
        register = "GB-COH"
        cleaned_name = re.sub(r"\s*\(Company No\.\s*\d+\)", "", name).strip()
        return reg_nr, register, cleaned_name
    return None, None, name


def process_visit(dataset, item: Dict[str, Any], member):
    """Process Category 5 (Visits outside the UK) - creates Trip and Payment(s)."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Create Trip entity
    trip = dataset.make("Trip")
    trip.id = dataset.make_id("visit", item_id)
    trip.add("recordId", str(item_id))

    # Add MP as participant
    trip.add("involved", member)

    # Parse visit locations (nested field structure)
    countries = []
    destinations = []
    for field in item.get("fields", []):
        if field.get("name") == "VisitLocations" and field.get("values"):
            for location_fields in field.get("values", []):
                for loc_field in location_fields:
                    if loc_field.get("name") == "Country":
                        country = loc_field.get("value")
                        if country:
                            countries.append(country)
                    elif loc_field.get("name") == "Destination":
                        dest = loc_field.get("value")
                        if dest:
                            destinations.append(dest)

    # Name: summary or purpose
    trip.add("name", item.get("summary") or fields_data.get("Purpose"))
    trip.add("summary", fields_data.get("Purpose"))

    # Dates
    start_date = fields_data.get("StartDate")
    end_date = fields_data.get("EndDate")
    if start_date:
        trip.add("startDate", parse_date(start_date))
    if end_date:
        trip.add("endDate", parse_date(end_date))

    # Location
    for country in countries:
        trip.add("country", country)
    for dest in destinations:
        trip.add("location", dest)

    # Parse donors/sponsors from nested Donors array
    donors = []
    for field in item.get("fields", []):
        if field.get("name") == "Donors" and field.get("values"):
            for donor_fields_list in field.get("values", []):
                donor_data = {}
                for donor_field in donor_fields_list:
                    name = donor_field.get("name")
                    value = donor_field.get("value")
                    if name:
                        donor_data[name] = value
                    # Also capture currency from typeInfo
                    if name == "Value" and donor_field.get("typeInfo"):
                        donor_data["Currency"] = donor_field.get("typeInfo", {}).get(
                            "currencyCode"
                        )
                donors.append(donor_data)

    # Process each donor - add as organizer to trip and create payment
    trip_desc_parts = []
    for idx, donor_data in enumerate(donors):
        donor_name = donor_data.get("Name")
        if not donor_name:
            continue

        # Extract company registration number from name
        reg_nr, register, cleaned_name = extract_company_number(donor_name)

        donor_entity = make_legal_entity(
            dataset,
            name=cleaned_name,
            address=donor_data.get("PublicAddress"),
            schema="Organization"
            if not donor_data.get("IsPrivateIndividual")
            else "Person",
            reg_nr=reg_nr,
            register=register,
        )

        if donor_entity:
            # Add as organizer to trip
            trip.add("organizer", donor_entity)

            # Create payment entity
            payment = dataset.make("Payment")
            payment.id = dataset.make_id("visit_payment", item_id, idx)
            payment.add("recordId", f"{item_id}-{idx}")
            payment.add("beneficiary", member)
            payment.add("payer", donor_entity)

            amount = donor_data.get("Value")
            if amount:
                payment.add("amount", amount)
                currency = donor_data.get("Currency")
                if currency:
                    payment.add("currency", currency)

            if start_date:
                payment.add("date", parse_date(start_date))

            payment_desc = donor_data.get("PaymentDescription")
            payment_type = donor_data.get("PaymentType")
            if payment_desc:
                trip_desc_parts.append(payment_desc)
            purpose_parts = []
            if payment_type:
                purpose_parts.append(payment_type)
            if payment_desc:
                purpose_parts.append(payment_desc)
            if purpose_parts:
                payment.add("purpose", " - ".join(purpose_parts))
            if payment_desc:
                payment.add("description", payment_desc)

            payment.add(
                "summary", f"Visit: {fields_data.get('Purpose') or item.get('summary')}"
            )

            add_member_source_url(payment, item)

            dataset.emit(payment)

    if trip_desc_parts:
        trip.add("description", "\n".join(trip_desc_parts))

    add_member_source_url(trip, item)

    dataset.emit(trip)


def process_gift_foreign(dataset, item: Dict[str, Any], member):
    """Process Category 6 (Gifts from outside UK) - creates Payment (in-kind)."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    payment = dataset.make("Payment")
    payment.id = dataset.make_id("gift_foreign", item_id)
    payment.add("beneficiary", member)

    # Donor - check for company registration number
    donor_name = fields_data.get("DonorName")
    donor_country = fields_data.get("DonorCountry")
    if donor_name:
        # Extract company registration details if available
        reg_nr = fields_data.get("DonorCompanyIdentifier")
        register = None
        if (
            reg_nr
            and fields_data.get("DonorCompanyIdentifierSource") == "Companies House"
        ):
            register = "GB-COH"

        # Determine schema based on donor type
        donor_type = fields_data.get("DonorType")
        schema = "LegalEntity"
        if donor_type == "Company":
            schema = "Organization"
        elif donor_type == "Individual":
            schema = "Person"

        # Create donor with country in the schema parameter won't work,
        # so we create it and then add country property separately
        donor = dataset.make(schema)

        if reg_nr and register:
            donor.id = dataset.make_id(
                "entity", donor_name, reg_nr=reg_nr, register=register
            )
        else:
            donor.id = dataset.make_id("entity", donor_name)

        donor.add("name", donor_name)

        donor_address = fields_data.get("DonorPublicAddress")
        if donor_address:
            donor.add("address", donor_address)

        donor_summary = fields_data.get("DonorNatureOfBusiness")
        if donor_summary:
            donor.add("summary", donor_summary)

        if donor_country:
            donor.add("country", donor_country)

        donor.add("jurisdiction", "gb")
        dataset.emit(donor)

        payment.add("payer", donor)

    # Amount
    amount = fields_data.get("Value")
    if amount:
        payment.add("amount", amount)
        currency = get_currency(item, "Value")
        if currency:
            payment.add("currency", currency)

    # Dates
    date = get_payment_date(item, fields_data)
    if date:
        payment.add("date", date)

    # Description
    payment.add("purpose", fields_data.get("PaymentDescription"))
    payment.add("summary", item.get("summary"))

    add_member_source_url(payment, item)

    dataset.emit(payment)


def process_property(dataset, item: Dict[str, Any], member):
    """Process Category 7 (Land and property) - creates Ownership."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Create an Asset for the property
    asset = dataset.make("Asset")
    asset.id = dataset.make_id("property", item_id)

    location = fields_data.get("Location")
    prop_desc = fields_data.get("PropertyDescription")

    # Name from location and description
    name_parts = []
    if prop_desc:
        name_parts.append(prop_desc)
    if location:
        name_parts.append(f"in {location}")

    asset.add("name", " ".join(name_parts) if name_parts else item.get("summary"))
    asset.add("summary", item.get("summary"))
    asset.add("description", fields_data.get("PropertyOwnerDetails"))

    dataset.emit(asset)

    # Create Ownership relationship
    ownership = dataset.make("Ownership")
    ownership.id = dataset.make_id("ownership", item_id)
    ownership.add("owner", member)
    ownership.add("asset", asset)

    start_date = fields_data.get("StartDate")
    if start_date:
        ownership.add("startDate", parse_date(start_date))

    end_date = fields_data.get("EndDate")
    if end_date:
        ownership.add("endDate", parse_date(end_date))

    # Add rental income info to description if present
    rental_income = fields_data.get("RegistrableRentalIncome")
    if rental_income:
        ownership.add("description", f"Rental income: {rental_income}")

    dataset.emit(ownership)


def process_shareholding(dataset, item: Dict[str, Any], member):
    """Process Category 8 (Shareholdings) - creates Ownership."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Create the company as an Organization
    org_name = fields_data.get("OrganisationName")
    if not org_name:
        dataset.log.warning(f"No organization name for shareholding {item_id}")
        return

    company = make_legal_entity(
        dataset,
        name=org_name,
        summary=fields_data.get("OrganisationDescription"),
        schema="Organization",
    )

    # Create Ownership relationship
    ownership = dataset.make("Ownership")
    ownership.id = dataset.make_id("shareholding", item_id)
    ownership.add("owner", member)
    ownership.add("asset", company)

    # Add threshold information
    threshold = fields_data.get("ShareholdingThreshold")
    if threshold:
        ownership.add("description", threshold)

    # Dates
    reg_date = fields_data.get("RegistrableDate")
    if reg_date:
        ownership.add("startDate", parse_date(reg_date))

    end_date = fields_data.get("EndDate")
    if end_date:
        ownership.add("endDate", parse_date(end_date))

    # Additional context
    held_on_behalf = fields_data.get("HeldOnBehalfOf")
    managed_by = fields_data.get("ManagedBy")
    desc_parts = []
    if held_on_behalf:
        desc_parts.append(f"Held on behalf of: {held_on_behalf}")
    if managed_by:
        desc_parts.append(f"Managed by: {managed_by}")
    if desc_parts:
        existing_desc = ownership.get("description")
        if existing_desc:
            desc_parts.insert(0, existing_desc[0])
        ownership.set("description", "\n".join(desc_parts))

    dataset.emit(ownership)


def process_miscellaneous(dataset, item: Dict[str, Any], member):
    """Process Category 9 (Miscellaneous) - creates UnknownLink or similar."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Use UnknownLink for miscellaneous interests
    link = dataset.make("UnknownLink")
    link.id = dataset.make_id("misc", item_id)
    link.add("subject", member)

    # Try to identify if there's a related entity (donor)
    donor_name = fields_data.get("DonorName")
    if donor_name:
        donor = make_legal_entity(dataset, name=donor_name)
        if donor:
            link.add("object", donor)

    # Description
    description = fields_data.get("Description")
    misc_type = fields_data.get("MiscellaneousInterestType")

    desc_parts = []
    if misc_type:
        desc_parts.append(f"Type: {misc_type}")
    if description:
        desc_parts.append(description)

    link.add(
        "description", "\n".join(desc_parts) if desc_parts else item.get("summary")
    )
    link.add("summary", item.get("summary"))

    # Dates
    arose_date = fields_data.get("AroseOn")
    if arose_date:
        link.add("startDate", parse_date(arose_date))

    end_date = fields_data.get("EndDate")
    if end_date:
        link.add("endDate", parse_date(end_date))

    dataset.emit(link)


def process_family_employed(dataset, item: Dict[str, Any], member):
    """Process Category 10 (Family members employed) - creates Family + Employment."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Create Person for family member
    family_name = fields_data.get("PersonName")
    if not family_name:
        dataset.log.warning(f"No person name for family employment {item_id}")
        return

    family_member = dataset.make("Person")
    family_member.id = dataset.make_id("family", member.id, family_name)
    family_member.add("name", family_name)
    family_member.add("jurisdiction", "gb")
    dataset.emit(family_member)

    # Create Family relationship
    family_rel = dataset.make("Family")
    family_rel.id = dataset.make_id("family_rel", member.id, family_member.id)
    family_rel.add("person", member)
    family_rel.add("relative", family_member)

    relation_type = fields_data.get("FamilyRelationType")
    if relation_type:
        family_rel.add("relationship", relation_type)

    dataset.emit(family_rel)

    # Create Employment relationship (family member employed by MP)
    employment = dataset.make("Employment")
    employment.id = dataset.make_id("family_employment", item_id)
    employment.add("employee", family_member)
    employment.add("employer", member)

    job_title = fields_data.get("JobTitle")
    if job_title:
        employment.add("role", job_title)

    working_pattern = fields_data.get("WorkingPattern")
    if working_pattern:
        employment.add("description", f"Working pattern: {working_pattern}")

    end_date = fields_data.get("EndDate")
    if end_date:
        employment.add("endDate", parse_date(end_date))

    dataset.emit(employment)


def process_family_lobbying(dataset, item: Dict[str, Any], member):
    """Process Category 11 (Family members lobbying) - creates Family + Representation."""
    item_id = item.get("id")
    fields_data = get_fields(item)

    # Create Person for family member
    family_name = fields_data.get("PersonName")
    if not family_name:
        dataset.log.warning(f"No person name for family lobbying {item_id}")
        return

    family_member = dataset.make("Person")
    family_member.id = dataset.make_id("family", member.id, family_name)
    family_member.add("name", family_name)
    family_member.add("jurisdiction", "gb")
    dataset.emit(family_member)

    # Create Family relationship
    family_rel = dataset.make("Family")
    family_rel.id = dataset.make_id("family_rel", member.id, family_member.id)
    family_rel.add("person", member)
    family_rel.add("relative", family_member)

    relation_type = fields_data.get("FamilyRelationType")
    if relation_type:
        family_rel.add("relationship", relation_type)

    dataset.emit(family_rel)

    # Create employer organization
    employer_name = fields_data.get("Employer")
    if employer_name:
        employer = make_legal_entity(dataset, name=employer_name, schema="Organization")
        if employer:
            employer.add("topics", "role.lobby")
            dataset.emit(employer)

            # Create Employment for family member at lobbying firm
            employment = dataset.make("Employment")
            employment.id = dataset.make_id("family_lobby_employment", item_id)
            employment.add("employee", family_member)
            employment.add("employer", employer)

            job_title = fields_data.get("JobTitle")
            if job_title:
                employment.add("role", job_title)

            end_date = fields_data.get("EndDate")
            if end_date:
                employment.add("endDate", parse_date(end_date))

            dataset.emit(employment)

            # Create Representation relationship (lobbying)
            representation = dataset.make("Representation")
            representation.id = dataset.make_id("family_lobbying", item_id)
            representation.add("agent", family_member)
            representation.add("client", employer)
            representation.add("summary", item.get("summary"))
            dataset.emit(representation)


def crawl(dataset):
    """Main crawl entry point."""
    BASE_URL = "https://interests-api.parliament.uk/api/v1/Interests"

    PARAMS = {
        "PublishedFrom": "2024-01-01",
        "ExpandChildInterests": False,  # We handle nesting manually for reliability
        # "MemberId": 5069,  # Uncomment for testing with specific member
        "Take": 100,
        "Skip": 0,
    }

    while True:
        dataset.log.info(f"Crawling interests with params: {PARAMS}")
        data = dataset.fetch_json(BASE_URL, params=PARAMS, cache_days=7)

        if data is None:
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            item_id = item.get("id")
            category_data = item.get("category")
            if not category_data:
                continue

            category_id = category_data.get("id")
            member_data = item.get("member")

            # Create member entity
            member = make_mp(dataset, member_data)
            if not member:
                continue

            # Route to appropriate processor based on category
            if category_id == 12:
                # Employment and earnings (parent)
                fields_data, employer = process_employment(dataset, item, member)
                PARENT_CACHE[item_id] = (fields_data, employer)

            elif category_id in [1, 2]:
                # Employment payments (child of category 12)
                parent_id = item.get("parentInterestId")
                employer = None
                if parent_id:
                    if parent_id in PARENT_CACHE:
                        _, employer = PARENT_CACHE[parent_id]
                    else:
                        # Fetch and cache parent details if missing from current crawl stream
                        parent_item = fetch_interest(dataset, parent_id)
                        if parent_item:
                            p_member_data = parent_item.get("member")
                            p_member = make_mp(dataset, p_member_data)
                            p_fields, p_employer = process_employment(
                                dataset, parent_item, p_member
                            )
                            PARENT_CACHE[parent_id] = (p_fields, p_employer)
                            employer = p_employer

                process_payment(dataset, item, member, employer)

            elif category_id == 3:
                # Donations and other support
                process_donation(dataset, item, member)

            elif category_id == 4:
                # Gifts from UK sources
                process_gift_uk(dataset, item, member)

            elif category_id == 5:
                # Visits outside the UK
                process_visit(dataset, item, member)

            elif category_id == 6:
                # Gifts from outside the UK
                process_gift_foreign(dataset, item, member)

            elif category_id == 7:
                # Land and property
                process_property(dataset, item, member)

            elif category_id == 8:
                # Shareholdings
                process_shareholding(dataset, item, member)

            elif category_id == 9:
                # Miscellaneous
                process_miscellaneous(dataset, item, member)

            elif category_id == 10:
                # Family members employed
                process_family_employed(dataset, item, member)

            elif category_id == 11:
                # Family members engaged in lobbying
                process_family_lobbying(dataset, item, member)

            else:
                dataset.log.warning(f"Unknown category ID: {category_id}")

        # Advance pagination
        PARAMS["Skip"] += PARAMS["Take"]
        total = data.get("totalResults", 0)
        if PARAMS["Skip"] >= total:
            break


if __name__ == "__main__":
    pass
