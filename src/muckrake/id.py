import re
import hashlib
from typing import Optional, Any

from muckrake.utils import normalize_gb_coh



def make_hashed_id(prefix: str, *parts: Any) -> str:
    """Create a stable hashed ID prefixed by the dataset prefix."""
    digest = hashlib.sha1(prefix.encode("utf-8"))
    for part in (p for p in parts if p is not None):
        # Ensure we don't hash string representations of lists/brackets
        if isinstance(part, (list, set, tuple)):
            for p in part:
                digest.update(str(p).encode("utf-8"))
        else:
            digest.update(str(part).encode("utf-8"))
    return f"{prefix}-{digest.hexdigest()}"


# Pattern for org-id.guide identifiers: [ISO]-[REGISTER]-[ID]
# e.g. GB-COH-09506232
ORG_ID_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z0-9]+-[A-Z0-9]+$")

def is_org_id(identifier: str) -> bool:
    """Check if an ID follows the org-id.guide standard."""
    return bool(ORG_ID_PATTERN.match(identifier))

def make_org_id(reg_nr: Any, register: str = "GB-COH") -> Optional[str]:
    """Create a normalized org-id identifier from a registration number."""
    if reg_nr is None:
        return None

    # Handle cases where reg_nr might be a list (e.g. from scrapers or FtM properties)
    if isinstance(reg_nr, (list, set, tuple)):
        if not reg_nr:
            return None
        reg_nr = list(reg_nr)[0]

    # Basic cleanup
    reg_nr = str(reg_nr).strip().upper()
    if not reg_nr or reg_nr.lower() in ("nan", "none", "n/a"):
        return None

    # Register-specific normalization
    if register == "GB-COH":
        reg_nr = normalize_gb_coh(reg_nr)
        if reg_nr is None:
            return None

    return f"{register}-{reg_nr}"
