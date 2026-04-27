import csv
from urllib.parse import urlencode
from muckrake.util import parse_amount, parse_date
from .common import make_donor, create_recipient_entity


def build_url(base, params):
    parts = []
    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                parts.append((key, item))
        else:
            parts.append((key, value))
    return f"{base}?{urlencode(parts)}"


def crawl_donations(dataset):
    """Crawl political donations from the Electoral Commission."""
    BASE_URL = "https://search.electoralcommission.org.uk/api/csv/Donations"
    PARAMS = {
        "query": "",
        "sort": "AcceptedDate",
        "order": "desc",
        "et": ["pp", "ppm", "tp", "perpar", "rd"],
        "date": "Reported",
        # "from": "2025-01-01",
        "to": "",
        "rptPd": "",
        "prePoll": "false",
        "postPoll": "true",
        "register": ["gb", "ni", "none"],
        "donorStatus": [
            "tradeunion",
            "company",
            "unincorporatedassociation",
            "publicfund",
            "other",
            "registeredpoliticalparty",
            "friendlysociety",
            "trust",
            "limitedliabilitypartnership",
            "na",
            "unidentifiabledonor",
            "buildingsociety",
        ],  # we're filtering out "individual" donor status due to data protection concerns, to remove when we sort it out
        "isIrishSourceYes": "true",
        "isIrishSourceNo": "true",
        "includeOutsideSection75": "true",
    }

    dataset.log.info(f"Crawling donations with params: {PARAMS}")
    url = build_url(BASE_URL, PARAMS)
    path = dataset.fetch_resource("donations.csv", url)

    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            # Parse donor/recipient data
            donor_id = row.get("DonorId")
            donor_name = row.get("DonorName")
            donor_reg_nr = row.get("CompanyRegistrationNumber")
            donor_status = row.get("DonorStatus")
            donor_postcode = row.get("Postcode")

            recipient_id = row.get("RegulatedEntityId")
            recipient_name = row.get("RegulatedEntityName")
            recipient_type = row.get("RegulatedEntityType")
            recipient_donnee_type = row.get("RegulatedDoneeType")

            register_name = row.get("RegisterName")

            # Parse payment data
            pay_ec_ref = row.get("ECRef")
            pay_url = f"https://search.electoralcommission.org.uk/English/Donations/{pay_ec_ref}"
            pay_value = row.get("Value")
            pay_date_accepted = row.get("AcceptedDate")
            pay_type = row.get("DonationType")
            pay_nature = row.get("NatureOfDonation")
            pay_visit_purpose = row.get("PurposeOfVisit")

            # Create entities
            donor = make_donor(
                dataset,
                donor_id,
                donor_name,
                donor_status,
                donor_reg_nr,
                donor_postcode,
                register_name,
            )
            dataset.emit(donor)

            recipient = create_recipient_entity(
                dataset,
                recipient_id=recipient_id,
                recipient_name=recipient_name,
                recipient_type=recipient_type,
                recipient_donnee_type=recipient_donnee_type,
                register_name=register_name,
            )
            dataset.emit(recipient)

            # Create Donation
            payment = dataset.make("Donation")
            payment.id = dataset.make_id(pay_ec_ref)
            payment.add("programme", "Donation")
            payment.add("payer", donor)
            payment.add("beneficiary", recipient)
            payment.add("recordId", pay_ec_ref)
            payment.add("date", parse_date(pay_date_accepted))
            payment.add("amount", parse_amount(pay_value))
            payment.add("currency", "GBP")

            if pay_nature:
                payment.add("purpose", pay_nature)
            elif pay_visit_purpose:
                payment.add("purpose", pay_visit_purpose)

            if pay_type:
                payment.add("summary", pay_type)

            description_parts = []
            if pay_visit_purpose:
                description_parts.append(f"Purpose of Visit: {pay_visit_purpose}")
            if pay_nature:
                description_parts.append(f"Nature of Donation: {pay_nature}")
            if description_parts:
                payment.add("description", " | ".join(description_parts))

            payment.add("sourceUrl", pay_url)

            dataset.emit(payment)
