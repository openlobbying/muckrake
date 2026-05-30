import os
from pathlib import Path

from muckrake.env import find_env_file, load_env_file

# Base directory of the project
BASE_PATH = Path(__file__).parent.parent.parent


def _normalize_database_url(url: str | None) -> str | None:
    if url is None:
        return None
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


if os.getenv("ENVIRONMENT") != "production":
    env_file = find_env_file(fallback_paths=[BASE_PATH / ".env"])
    if env_file is not None:
        load_env_file(env_file)


def _require_database_url(name: str) -> str:
    value = _normalize_database_url(os.getenv(name))
    if value is None:
        raise RuntimeError(f"{name} must be set")
    return value


def _default_sqlite_uri(filename: str) -> str:
    return f"sqlite:///{(DATA_PATH / filename).as_posix()}"


DATA_PATH = Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))
ARTIFACT_PATH = Path(os.getenv("MUCKRAKE_ARTIFACT_PATH", DATA_PATH / "artifacts"))
SQL_URI: str = _normalize_database_url(os.getenv("MUCKRAKE_DATABASE_URL")) or _default_sqlite_uri(
    "muckrake.db"
)
PUBLISHED_SQL_URI: str = (
    _normalize_database_url(os.getenv("MUCKRAKE_PUBLISHED_DATABASE_URL")) or SQL_URI
)

LEVEL_PATH = DATA_PATH / "leveldb"
