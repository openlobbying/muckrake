import os
from pathlib import Path

# Base directory of the project
BASE_PATH = Path(__file__).parent.parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def _normalize_database_url(url: str | None) -> str | None:
    if url is None:
        return None
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


_load_dotenv(BASE_PATH / ".env")

DATA_PATH = Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))
ARTIFACT_PATH = Path(os.getenv("MUCKRAKE_ARTIFACT_PATH", DATA_PATH / "artifacts"))
SQL_URI = _normalize_database_url(os.getenv("MUCKRAKE_DATABASE_URL"))
if SQL_URI is None:
    raise RuntimeError("MUCKRAKE_DATABASE_URL must be set")
PUBLISHED_SQL_URI = _normalize_database_url(
    os.getenv("MUCKRAKE_PUBLISHED_DATABASE_URL")
) or SQL_URI

LEVEL_PATH = DATA_PATH / "leveldb"
ACTOR_SCHEMATA = {"LegalEntity", "Person", "Organization", "Company", "PublicBody"}
SEARCH_LIMIT = 25
