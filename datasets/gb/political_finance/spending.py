import csv
from muckrake.util import parse_amount, parse_date
from .common import make_donor, create_recipient_entity


def crawl_spending(dataset):
    """Crawl political spending/expenditure from the Electoral Commission."""
    url = "https://search.electoralcommission.org.uk/api/csv/Spending?start={start}&rows={pageSize}&query=&sort=DateIncurred&order=desc&et=pp&et=ppm&et=tp&et=perpar&et=rd&date=&from=&to=&rptPd=&prePoll=false&postPoll=false&isIrishSourceYes=true&isIrishSourceNo=true&includeOutsideSection75=true"

    path = dataset.fetch_resource("spending.csv", url)

    with open(path, 'r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            ec_ref = row.get('ECRef')
            if not ec_ref:
                continue

            # Regulated entity (the organisation that incurred the expenditure)
            recipient_id = row.get('RegulatedEntityId')
            recipient_name = row.get('RegulatedEntityName')
            recipient_type = row.get('RegulatedEntityType')

            # Supplier / payee
            supplier_id = row.get('SupplierId')
            supplier_name = row.get('SupplierName')
            supplier_address = row.get('FullAddress')

            # Spending/payment fields
            total_expenditure = row.get('TotalExpenditure')
            date_incurred = row.get('DateIncurred')
            expense_category = row.get('ExpenseCategoryName')
            amount_england = row.get('AmountInEngland')
            amount_scotland = row.get('AmountInScotland')
            amount_wales = row.get('AmountInWales')
            amount_ni = row.get('AmountInNorthernIreland')
            date_of_claim = row.get('DateOfClaimForPayment')
            date_paid = row.get('DatePaid')
            joint_campaign = row.get('JointCampaignName')
            unregistered = row.get('UnregisteredCampaignerName')
            campaigning_name = row.get('CampaigningName')
            is_outside_section75 = row.get('IsOutsideSection75')

            # Create entities
            supplier = make_donor(
                dataset, supplier_id, supplier_name, None,
                None, supplier_address, None
            )
            dataset.emit(supplier)

            recipient = create_recipient_entity(
                dataset, recipient_id, recipient_name, recipient_type, None
            )
            dataset.emit(recipient)

            # Create Payment record representing the expenditure
            payment = dataset.make('Payment')
            payment.id = dataset.make_id(ec_ref)
            payment.add('purpose', 'Spending')
            payment.add('payer', supplier)
            payment.add('beneficiary', recipient)
            payment.add('recordId', ec_ref)
            payment.add('date', parse_date(date_incurred))
            payment.add('amount', parse_amount(total_expenditure))
            payment.add('currency', 'GBP')

            # Summary and description
            if expense_category:
                payment.add('summary', expense_category)

            description_parts = []
            # Avoid duplicating information already stored in other fields
            # (supplier name/address and dates are captured separately on entities/records).
            if joint_campaign:
                description_parts.append(f"Joint campaign: {joint_campaign}")
            if unregistered:
                description_parts.append(f"Unregistered campaigner: {unregistered}")
            if campaigning_name:
                description_parts.append(f"Campaigning name: {campaigning_name}")
            if is_outside_section75:
                description_parts.append(f"Outside section75: {is_outside_section75}")

            # Breakdown by country where available
            breakdown = []
            if amount_england:
                breakdown.append(f"England: £{amount_england}")
            if amount_scotland:
                breakdown.append(f"Scotland: £{amount_scotland}")
            if amount_wales:
                breakdown.append(f"Wales: £{amount_wales}")
            if amount_ni:
                breakdown.append(f"Northern Ireland: £{amount_ni}")
            if breakdown:
                description_parts.append('Breakdown: ' + ' | '.join(breakdown))

            if description_parts:
                payment.add('description', ' | '.join(description_parts))

            source_url = f'https://search.electoralcommission.org.uk/English/Spending/{ec_ref}'
            payment.add('sourceUrl', source_url)

            dataset.emit(payment)
