"""Common entity creation functions for Electoral Commission data."""
from typing import Optional

from muckrake.utils import normalize_gb_coh

def make_donor(
    dataset,
    donor_id: Optional[str],
    donor_name: Optional[str],
    donor_status: Optional[str],
    donor_reg_nr: Optional[str],
    donor_postcode: Optional[str],
    register_name: Optional[str]
):
    """Create a donor/lender entity with proper schema and properties."""
    # Apply manual corrections from datapatch lookups
    if donor_name:
        result = dataset.lookup("donor_reg_nr", donor_name)
        if result is not None:
            donor_reg_nr = result.value
    
    donor_schema = 'LegalEntity'
    if donor_status == 'Individual':
        donor_schema = 'Person'
    elif donor_status in ('Company', 'Limited Liability Partnership'):
        donor_schema = 'Company'
    elif donor_status in ('Registered Political Party', 'Unincorporated Association', 
                          'Trade Union', 'Trust', 'Friendly Society'):
        donor_schema = 'Organization'
    elif donor_status == 'Public Fund':
        donor_schema = 'PublicBody'

    donor = dataset.make(donor_schema)
    # donor.id = dataset.make_id('donor', donor_id or donor_name)
    if donor_reg_nr:
        donor_reg_nr = normalize_gb_coh(donor_reg_nr)
    
    donor.id = dataset.make_id('donor', donor_id, reg_nr=donor_reg_nr, register = "GB-COH")

    if donor_reg_nr:
        donor.add('registrationNumber', f"GB-COH-{normalize_gb_coh(donor_reg_nr)}")
    
    donor.add('name', donor_name)
    donor.add('address', donor_postcode)        
    
    if donor_status:
        if donor_status == 'Registered Political Party':
            donor.add('topics', 'pol.party')
        elif donor_status == 'Public Fund':
            donor.add('topics', 'gov')
        elif donor_status == 'Trade Union':
            donor.add('topics', 'pol.union')
        elif donor_status in ('Limited Liability Partnership', 'Unincorporated Association', 
                             'Friendly Society', 'Trust'):
            donor.add('legalForm', donor_status)
    
    if register_name == 'Great Britain':
        donor.add('jurisdiction', 'gb')
    elif register_name == 'Northern Ireland':
        donor.add('jurisdiction', 'gb-nir')
    
    return donor


def create_recipient_entity(
    dataset,
    recipient_id: Optional[str],
    recipient_name: Optional[str],
    recipient_type: Optional[str],
    recipient_donnee_type: Optional[str],
    register_name: Optional[str]
):
    """Create a recipient entity (political party or other regulated entity)."""
    recipient_schema = 'Person'
    if recipient_type == 'Political Party':
        recipient_schema = 'Organization'
    if recipient_donnee_type == 'Members Association':
        recipient_schema = 'Organization'
    
    recipient = dataset.make(recipient_schema)
    recipient.id = dataset.make_id('recipient', recipient_id)
    recipient.add('name', recipient_name)
    
    if recipient_type == 'Political Party':
        recipient.add('topics', 'pol.party')
    
    if recipient_donnee_type in ('MSP - Member of the Scottish Parliament',
                                 'MP - Member of Parliament',
                                 'Senedd Member',
                                 'Cllr. - Member of a Local Authority',
                                 'MLA - Member of the Legislative Authority of Northern Ireland'):
        recipient.add('topics', 'role.pep')
    
    if recipient_donnee_type == 'MSP - Member of the Scottish Parliament':
        recipient.add('jurisdiction', 'gb-sct')
    elif recipient_donnee_type == 'Senedd Member':
        recipient.add('jurisdiction', 'gb-wls')
    elif recipient_donnee_type == 'MLA - Member of the Legislative Authority of Northern Ireland':
        recipient.add('jurisdiction', 'gb-nir')
    elif recipient_donnee_type in ('MP - Member of Parliament',
                                 'Cllr. - Member of a Local Authority'):
        recipient.add('jurisdiction', 'gb')
    
    if register_name == 'Great Britain':
        recipient.add('jurisdiction', 'gb')
    elif register_name == 'Northern Ireland':
        recipient.add('jurisdiction', 'gb-nir')
    
    return recipient