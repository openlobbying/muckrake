import csv
from muckrake.util import parse_amount, parse_date
from .common import make_donor, create_recipient_entity


def crawl_donations(dataset):
    """Crawl political donations from the Electoral Commission."""
    # url = "https://search.electoralcommission.org.uk/api/csv/Donations?query=&sort=AcceptedDate&order=desc&et=pp&et=ppm&et=tp&et=perpar&et=rd&date=Reported&from=&to=&rptPd=&prePoll=false&postPoll=true&register=gb&register=ni&register=none&&isIrishSourceYes=true&isIrishSourceNo=true&includeOutsideSection75=true"
    url = "https://search.electoralcommission.org.uk/api/csv/Donations?start={start}&rows={pageSize}&query=&sort=AcceptedDate&order=desc&et=pp&et=ppm&et=tp&et=perpar&et=rd&date=Reported&from=&to=&rptPd=&prePoll=false&postPoll=true&quarters=2026Q1234&quarters=2025Q1234&register=gb&register=ni&register=none&period=3951&period=3953&period=3891&period=3898&period=3889&period=3897&period=3887&period=3896&period=3885&period=3895&period=3883&period=3894&period=3881&period=3893&period=3874&period=3865&period=3862&period=3810&period=3765&period=3767&period=3718&period=3720&period=3714&period=3716&period=3710&period=3712&period=3706&period=3708&period=3702&period=3704&period=3698&period=3700&period=3676&period=3695&period=3604&period=3602&period=3598&period=3600&period=3594&period=3596&period=3578&period=3580&period=3574&period=3576&period=3570&period=3572&period=3559&period=3524&period=3567&period=3522&period=3520&period=3518&period=2513&period=2507&period=2509&period=2511&period=1485&period=1487&period=1480&period=1481&period=1477&period=1478&period=1474&period=1476&period=1471&period=1473&period=463&period=1466&period=1465&period=460&period=444&period=447&period=442&period=438&period=434&period=409&period=427&period=403&period=288&period=300&period=302&period=304&period=280&period=218&period=206&period=208&period=137&period=138&period=128&period=73&period=69&period=61&period=63&period=50&period=39&period=40&period=5&isIrishSourceYes=true&isIrishSourceNo=true&includeOutsideSection75=true"

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

            # Create Payment
            payment = dataset.make("Payment")
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
