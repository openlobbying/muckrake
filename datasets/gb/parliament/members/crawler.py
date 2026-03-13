from ..util import make_house

def crawl(dataset):

    BASE_URL = "https://members-api.parliament.uk/api/Members/Search"
    
    PARAMS = {
        "skip": 0,
        "take": 20,
        "MembershipInDateRange.WasMemberOnOrAfter": "2025-01-01"
        }
    
    while True:
        dataset.log.info(f"Crawling members with params: {PARAMS}")
        data = dataset.fetch_json(BASE_URL, params=PARAMS, cache_days=7)
        if data is None:
            break
            
        results = data.get('items', [])
        if not results:
            break
            
        for result in results:
                item = result.get('value')
                if not item:
                    continue

                # create entity
                member = dataset.make('Person')

                # assign ID
                member_id = item.get('id')
                member.id = dataset.make_id('member', member_id, reg_nr=member_id, register='GB-MEMBER')
                member.add('sourceUrl', f"https://members.parliament.uk/member/{member_id}")

                # assign name
                member.add('name', item.get('nameDisplayAs'))
                member.add('name', item.get('nameFullTitle'))
                member.add('name', item.get('nameListAs'))

                # gender
                gender = item.get('gender')
                if gender == 'F':
                    member.add('gender', 'female')
                elif gender == 'M':
                    member.add('gender', 'male')
                
                # other bits
                member.add('jurisdiction', 'gb')
                member.add('topics', 'role.pep')
                

                # # GET MORE BIOGRAPHY DETAILS
                url_bio = f"https://members-api.parliament.uk/api/Members/{item.get('id')}/Biography"
                data_bio = dataset.fetch_json(url_bio, cache_days=30)
                
                dataset.log.debug(f"Crawled biography data for member {member_id}: {url_bio}")
                bio_value = data_bio.get('value')
                
                # HOUSE
                # TODO: add constituencies
                bio_houses = bio_value.get('houseMemberships', [])
                for house_info in bio_houses:
                    # create house membership
                    house_membership = dataset.make('Membership')
                    house_membership.id = dataset.make_id('house_membership', member_id, house_info.get('name'))
                    house_membership.add('member', member)

                    house_membership.add('startDate', house_info.get('startDate'))
                    if house_info.get('endDate'):
                        house_membership.add('endDate', house_info.get('endDate'))

                    # create house
                    if house_info.get('name') == "Joint":
                        # create both houses as parents
                        commons = make_house(dataset, "Commons")
                        house_membership.add('organization', commons)
                        lords = make_house(dataset, "Lords")
                        house_membership.add('organization', lords)
                    else:
                        house = make_house(dataset, house_info.get('name'))
                        house_membership.add('organization', house)
                    
                    dataset.emit(house_membership)
                
                # GOVERNMENT POSTS
                bio_posts = bio_value.get('governmentPosts', []) + bio_value.get('oppositionPosts', []) + bio_value.get('otherPosts', [])
                for post in bio_posts:
                    # create government employment
                    gov_employment = dataset.make('Employment')
                    gov_employment.id = dataset.make_id('post', member_id, post.get('id'))

                    gov_employment_house = post.get('house')
                    if gov_employment_house == 3:  # Joint
                        # create both houses as parents
                        commons = make_house(dataset, "Commons")
                        gov_employment.add('employer', commons)
                        lords = make_house(dataset, "Lords")
                        gov_employment.add('employer', lords)
                    elif gov_employment_house in (1, 2):
                        house = make_house(dataset, gov_employment_house)
                        gov_employment.add('employer', house)
                    
                    gov_employment.add('employee', member)
                    gov_employment.add('role', post.get('name'))
                    gov_employment.add('startDate', post.get('startDate'))
                    if post.get('endDate'):
                        gov_employment.add('endDate', post.get('endDate'))
                    
                    dataset.emit(gov_employment)

                # PARTY
                bio_parties = bio_value.get('partyAffiliations')
                for party_info in bio_parties:
                    # create party
                    party = dataset.make('Organization')
                    party_id = party_info.get('id')
                    party.id = dataset.make_id('party', party_id, reg_nr=party_id, register='GB-PARTY')
                    party.add('name', party_info.get('name'))                    
                    party.add('jurisdiction', 'gb')
                    party.add('topics', 'pol.party')
                    dataset.emit(party)

                    # create party membership
                    party_membership = dataset.make('Membership')
                    party_membership.id = dataset.make_id('party_membership', member_id, party_id)
                    party_membership.add('member', member)
                    party_membership.add('organization', party)
                    party_membership.add('role', f"Member of {party_info.get('name')}")
                    party_membership.add('startDate', party_info.get('startDate'))
                    if party_info.get('endDate'):
                        party_membership.add('endDate', party_info.get('endDate'))
                    dataset.emit(party_membership)
                
                # COMMITTEES
                bio_committees = bio_value.get('committeeMemberships', [])
                for committee_info in bio_committees:
                    # create committee
                    committee = dataset.make('PublicBody')
                    committee_id = committee_info.get('id')
                    committee.id = dataset.make_id('committee', committee_id, reg_nr=committee_id, register='GB-CMTE')
                    committee.add('sourceUrl', f"https://committees.parliament.uk/committee/{committee_id}")
                    committee.add('name', committee_info.get('name'))
                    dataset.emit(committee)

                    # create committee membership
                    committee_membership = dataset.make('Membership')
                    committee_membership.id = dataset.make_id('committee_membership', member_id, committee_id)
                    committee_membership.add('member', member)
                    committee_membership.add('organization', committee)
                    committee_membership.add('startDate', committee_info.get('startDate'))
                    if committee_info.get('endDate'):
                        committee_membership.add('endDate', committee_info.get('endDate'))
                    dataset.emit(committee_membership)

                dataset.emit(member)
            
        PARAMS["skip"] += PARAMS["take"]

if __name__ == "__main__":
    # Test stub if needed
    pass
