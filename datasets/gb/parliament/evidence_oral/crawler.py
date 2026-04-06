from ..util import (
    make_committee,
    make_witness_org,
    make_witness_person,
    make_witness_employment,
    make_evidence_event,
)


def crawl(dataset):
    BASE_URL = "https://committees-api.parliament.uk/api/OralEvidence"

    PARAMS = {
        "skip": 0,
        "take": 30,
        # "StartDate": "2025-01-01"
        }

    while True:
        dataset.log.info(f"Crawling oral evidence with params: {PARAMS}")
        data = dataset.fetch_json(BASE_URL, params=PARAMS, cache_days=7)
        if data is None:
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            # create event
            oral_evidence = make_evidence_event(dataset, item, type="oral")
            evidence_id = item.get("id")
            evidence_source_url = (
                f"https://committees.parliament.uk/oralevidence/{evidence_id}/html/"
                if evidence_id is not None
                else None
            )
            evidence_date = (
                item.get("meetingDate")
                or item.get("activityStartDate")
                or item.get("publicationDate")
            )

            # create committee
            committees = item.get("committees") or []
            for committee in committees:
                comm_entity = make_committee(dataset, committee)
                oral_evidence.add("organizer", comm_entity)

            # create witnesses
            witnesses = item.get("witnesses") or []
            for witness in witnesses:
                witness_pers = None
                if witness.get("submitterType") == "Individual":
                    witness_pers = make_witness_person(dataset, witness)
                    oral_evidence.add("involved", witness_pers)

                # create witness org
                orgs = witness.get("organisations") or []
                for org_item in orgs:
                    witness_org = make_witness_org(dataset, org_item)
                    oral_evidence.add("involved", witness_org)

                    # create employment (only if we have a person)
                    if witness_pers is not None:
                        witness_id = witness.get("id") or witness.get("personId")
                        org_id = org_item.get("cisId") or org_item.get("name")
                        record_id = None
                        if (
                            evidence_id is not None
                            and witness_id is not None
                            and org_id
                        ):
                            record_id = f"oral:{evidence_id}:{witness_id}:{org_id}"
                        make_witness_employment(
                            dataset,
                            witness_pers,
                            witness_org,
                            org_item.get("role"),
                            source_url=evidence_source_url,
                            date=evidence_date,
                            record_id=record_id,
                        )

            # emit oral evidence event
            dataset.emit(oral_evidence)

        PARAMS["skip"] += PARAMS["take"]


if __name__ == "__main__":
    pass
