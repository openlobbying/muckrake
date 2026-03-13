# committee
def make_committee(dataset, item):
    # create entity
    committee = dataset.make("PublicBody")

    # assign ID
    committee_id = item.get("id")
    committee.id = dataset.make_id(
        "committee", committee_id, reg_nr=committee_id, register="GB-CMTE"
    )

    committee.add(
        "sourceUrl", f"https://committees.parliament.uk/committee/{committee_id}"
    )

    # assign name
    committee.add("name", item.get("name"))

    previous_names = item.get("nameHistory", [])
    if previous_names:
        for prev in previous_names:
            prev_name = prev.get("name")
            if prev_name and prev_name != item.get("name"):
                committee.add("previousName", prev_name)

    # contacts
    committee_contacts = item.get("contact", {})
    if committee_contacts:
        committee.add("email", committee_contacts.get("email"))
        committee.add("phone", committee_contacts.get("phone"))
        committee.add("address", committee_contacts.get("address"))

    # date
    committee.add("incorporationDate", item.get("startDate"))
    if item.get("endDate"):
        committee.add("dissolutionDate", item.get("endDate"))

    # other bits
    committee.add("jurisdiction", "gb")
    committee.add("topics", "gov.legislative")
    committee.add("topics", "gov.legislative.committee")

    # make house
    if item.get("house") == "Joint":
        # create both houses as parents
        commons = make_house(dataset, "Commons")
        committee.add("parent", commons)
        lords = make_house(dataset, "Lords")
        committee.add("parent", lords)
    else:
        house = make_house(dataset, item.get("house"))
        committee.add("parent", house)

    # make subcommittee
    subcommittees = item.get("subCommittees", [])
    if subcommittees:
        for sub_item in subcommittees:
            sub_committee = make_committee(dataset, sub_item)
            if sub_committee:
                sub_committee.add("parent", committee)
                # We re-emit the sub_committee to save the parent relationship
            dataset.emit(sub_committee)

    # make parent committee
    parent_data = item.get("parentCommittee")
    if parent_data:
        # If it's a single object, wrap it in a list to use the same logic
        if isinstance(parent_data, dict):
            parent_data = [parent_data]

        for parent_item in parent_data:
            parent_committee = make_committee(dataset, parent_item)
            if parent_committee:
                committee.add("parent", parent_committee)

    # emit
    dataset.emit(committee)
    return committee


# house
def make_house(dataset, house_name):
    # create entity
    house = dataset.make("PublicBody")

    if house_name in ("Commons", 1):
        house.id = dataset.make_id("house", house_name, reg_nr="1", register="GB-PARL")
        house.add("name", "House of Commons")
    elif house_name in ("Lords", 2):
        house.id = dataset.make_id("house", house_name, reg_nr="2", register="GB-PARL")
        house.add("name", "House of Lords")
    else:
        dataset.log.error(f"Unknown house name: {house_name}")
        return None
    # elif house_name == "Joint":
    #     house.id = dataset.make_id('house', house_name, reg_nr = '1', register='GB-PARL')
    #     house.id = dataset.make_id('house', house_name, reg_nr = '2', register='GB-PARL')

    house.add("name", house_name)
    house.add("jurisdiction", "gb")
    house.add("topics", "gov.legislative")

    dataset.emit(house)
    return house


# party
def make_party(dataset, item):
    # create entity
    party = dataset.make("Organization")

    # assign ID
    party_id = item.get("id")
    party.id = dataset.make_id("party", party_id, reg_nr=party_id, register="GB-PARTY")

    # assign name
    party.add("name", item.get("name"))
    party.add("abbreviation", item.get("abbreviation"))

    # other bits
    party.add("jurisdiction", "gb")
    party.add("topics", "role.party")

    dataset.emit(party)
    return party


def make_party_membership(dataset, member, party):
    # create entity
    party_membership = dataset.make("Membership")

    # assign ID
    party_membership.id = dataset.make_id("party_membership", member.id, party.id)

    # assign participants
    party_membership.add("member", member)
    party_membership.add("organization", party)
    party_membership.add("role", f"Member of {party.get('name')}")

    dataset.emit(party_membership)
    return party_membership


# witness person
def make_witness_person(dataset, item):
    witness_pers = dataset.make("Person")

    witness_person_id = item.get("personId") or item.get("name")
    witness_pers.id = dataset.make_id("witness_person", witness_person_id)

    witness_pers.add("name", item.get("name"))

    witness_pers.add("jurisdiction", "gb")

    dataset.emit(witness_pers)
    return witness_pers


# witness org
def make_witness_org(dataset, item):
    witness_org = dataset.make("Organization")

    witness_org_id = item.get("cisId") or item.get("name")
    witness_org.id = dataset.make_id("witness_org", witness_org_id)

    witness_org.add("name", item.get("name"))

    witness_org.add("jurisdiction", "gb")

    dataset.emit(witness_org)
    return witness_org


# witness employment
def make_witness_employment(
    dataset,
    person,
    org,
    role,
    source_url=None,
    date=None,
    record_id=None,
):
    witness_employment = dataset.make("Employment")

    witness_employment.id = dataset.make_id("witness_employment", person.id, org.id)

    witness_employment.add("employee", person)
    witness_employment.add("employer", org)
    witness_employment.add("role", role)
    witness_employment.add("sourceUrl", source_url)
    witness_employment.add("date", date)
    witness_employment.add("recordId", record_id)

    dataset.emit(witness_employment)
    return witness_employment


def make_evidence_event(dataset, item, type):
    # create event
    event = dataset.make("Event")
    item_id = item.get("id")
    event.id = dataset.make_id(f"{type}_evidence", item_id)
    event.add(
        "sourceUrl", f"https://committees.parliament.uk/{type}evidence/{item_id}/html/"
    )

    businesses = item.get("committeeBusinesses") or []
    for business in businesses:
        event.add("name", business.get("title"))

    # written evidence only has one business
    if not businesses:
        business = item.get("committeeBusiness")
        if business:
            event.add("name", business.get("title"))

    meeting_date = item.get("meetingDate")
    activity_date = item.get("activityStartDate")
    publication_date = item.get("publicationDate")
    event.add("date", meeting_date or activity_date or publication_date)

    event.add("country", "gb")
    event.add("topics", "gov.legislative")
    event.add("topics", "gov.legislative.committee")
    event.add("keywords", f"{type.capitalize()} Evidence")

    dataset.emit(event)
    return event


# register of interests helpers
def make_mp(dataset, member_data):
    """Create a Person entity for an MP."""
    if not member_data:
        return None

    member = dataset.make("Person")
    member_id = member_data.get("id")
    member.id = dataset.make_id(
        "member", member_id, reg_nr=member_id, register="GB-MEMBER"
    )
    member.add("name", member_data.get("nameDisplayAs"))
    member.add("alias", member_data.get("nameListAs"))
    member.add("topics", "role.pep")
    member.add("jurisdiction", "gb")
    dataset.emit(member)
    return member


def make_legal_entity(
    dataset,
    name,
    address=None,
    summary=None,
    schema="LegalEntity",
    reg_nr=None,
    register=None,
):
    """Create a legal entity (Person, Organization, or LegalEntity) with given details.

    Args:
        dataset: Dataset context
        name: Entity name
        address: Optional address
        summary: Optional summary/description
        schema: FtM schema (LegalEntity, Organization, or Person)
        reg_nr: Optional registration number (e.g., Companies House number)
        register: Optional register identifier (e.g., 'GB-COH' for Companies House)
    """
    if not name:
        return None

    entity = dataset.make(schema)

    # Use structured org-id if registration number is provided
    if reg_nr and register:
        entity.id = dataset.make_id("entity", name, reg_nr=reg_nr, register=register)
    else:
        entity.id = dataset.make_id("entity", name)

    entity.add("name", name)

    if address:
        entity.add("address", address)
    if summary:
        entity.add("summary", summary)

    entity.add("jurisdiction", "gb")
    dataset.emit(entity)
    return entity
