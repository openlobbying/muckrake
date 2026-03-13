import re
from typing import Optional

# Companies House company number regex pattern
# Source: https://gist.github.com/rob-murray/01d43581114a6b319034732bcbda29e1
GB_COH_RE = re.compile(
    r"^(((AC|CE|CS|FC|FE|GE|GS|IC|LP|NC|NF|NI|NL|NO|NP|OC|OE|PC|R0|RC|SA|SC|SE|SF|SG|SI|SL|SO|SR|SZ|ZC|\d{2})\d{6})|((IP|SP|RS)[A-Z\d]{6})|(SL\d{5}[\dA])|(RS007853Z))$"
)


def is_gb_coh(company_number: str) -> bool:
    """Validate a UK Companies House company number."""
    if not company_number:
        return False
    return bool(GB_COH_RE.match(company_number))


def normalize_gb_coh(company_number: Optional[str]) -> Optional[str]:
    """Normalize and validate a UK Companies House company number."""
    if company_number is None:
        return None

    # Basic cleanup
    normalized = str(company_number).strip().upper()
    if not normalized:
        return None

    # Companies House numbers are 8 characters, often zero-padded
    # e.g. '12345' -> '00012345'
    if normalized.isdigit() and len(normalized) < 8:
        normalized = normalized.zfill(8)

    if is_gb_coh(normalized):
        return normalized

    return None