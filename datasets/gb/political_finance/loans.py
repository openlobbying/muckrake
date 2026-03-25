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


def crawl_loans(dataset):
    """Crawl political loans from the Electoral Commission."""
    BASE_URL = "https://search.electoralcommission.org.uk/api/csv/Loans"
    PARAMS = {
        "query": "",
        "sort": "StartDate",
        "order": "desc",
        "et": ["pp", "ppm", "tp", "perpar", "rd"],
        "date": "Start",
        "from": "",
        "to": "",
        "rptPd": "",
        "prePoll": "false",
        "postPoll": "false",
        "register": ["gb", "ni", "none"],
        "loanStatus": ["outstanding", "ended"],
        "isIrishSourceYes": "true",
        "isIrishSourceNo": "true",
        "includeOutsideSection75": "true",
    }

    dataset.log.info(f"Crawling loans with params: {PARAMS}")
    url = build_url(BASE_URL, PARAMS)
    path = dataset.fetch_resource("loans.csv", url)

    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            # Parse lender/recipient data
            lender_id = row.get("LoanParticipantId")
            lender_name = row.get("LoanParticipantName")
            lender_reg_nr = row.get("CompanyRegistrationNumber")
            lender_type = row.get("LoanParticipantType")
            lender_postcode = row.get("Postcode")

            recipient_id = row.get("RegulatedEntityId")
            recipient_name = row.get("RegulatedEntityName")
            recipient_type = row.get("RegulatedEntityType")

            register_name = row.get("RegisterName")

            # Parse loan data
            loan_ec_ref = row.get("ECRef")
            loan_url = (
                f"https://search.electoralcommission.org.uk/English/Loans/{loan_ec_ref}"
            )
            loan_value = row.get("Value")
            loan_start_date = row.get("StartDate")
            loan_end_date = row.get("EndDate")
            loan_status = row.get("LoanStatus")
            loan_type = row.get("LoanType")
            loan_interest = row.get("RateOfInterestDescription")
            amount_repaid = row.get("AmountRepaid")
            amount_converted = row.get("AmountConverted")
            amount_outstanding = row.get("AmountOutstanding")

            # Create entities
            lender = make_donor(
                dataset,
                lender_id,
                lender_name,
                lender_type,
                lender_reg_nr,
                lender_postcode,
                register_name,
            )
            dataset.emit(lender)

            recipient = create_recipient_entity(
                dataset,
                recipient_id=recipient_id,
                recipient_name=recipient_name,
                recipient_type=recipient_type,
                recipient_donnee_type=None,
                register_name=register_name,
            )
            dataset.emit(recipient)

            # Create Payment for the loan
            payment = dataset.make("Payment")
            payment.id = dataset.make_id(loan_ec_ref)
            payment.add("programme", "Loan")
            payment.add("payer", lender)
            payment.add("beneficiary", recipient)
            payment.add("recordId", loan_ec_ref)
            payment.add("date", parse_date(loan_start_date))
            payment.add("amount", parse_amount(loan_value))
            payment.add("currency", "GBP")

            if loan_type:
                payment.add("purpose", loan_type)

            # Build summary/description for loan
            summary_parts = ["Political Loan"]
            if loan_status:
                summary_parts.append(f"({loan_status})")
            payment.add("summary", " ".join(summary_parts))

            description_parts = []
            if loan_type:
                description_parts.append(f"Type: {loan_type}")
            if loan_interest:
                description_parts.append(f"Interest: {loan_interest}")
            if amount_repaid:
                description_parts.append(f"Repaid: £{amount_repaid}")
            if amount_converted:
                description_parts.append(f"Converted: £{amount_converted}")
            if amount_outstanding:
                description_parts.append(f"Outstanding: £{amount_outstanding}")
            if loan_end_date:
                description_parts.append(f"End date: {loan_end_date}")

            if description_parts:
                payment.add("description", " | ".join(description_parts))

            payment.add("sourceUrl", loan_url)

            dataset.emit(payment)