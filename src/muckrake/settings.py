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
    env_file = find_env_file()
    if env_file is not None:
        load_env_file(env_file)


def _current_data_path() -> Path:
    return Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))


def get_working_sql_uri() -> str:
    return (
        _normalize_database_url(os.getenv("MUCKRAKE_DATABASE_URL"))
        or f"sqlite:///{(_current_data_path() / 'muckrake.db').as_posix()}"
    )


def get_published_sql_uri() -> str:
    return (
        _normalize_database_url(os.getenv("MUCKRAKE_PUBLISHED_DATABASE_URL"))
        or get_working_sql_uri()
    )


DATA_PATH = Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))
ARTIFACT_PATH = Path(os.getenv("MUCKRAKE_ARTIFACT_PATH", DATA_PATH / "artifacts"))
SQL_URI: str = get_working_sql_uri()
PUBLISHED_SQL_URI: str = get_published_sql_uri()

LEVEL_PATH = DATA_PATH / "leveldb"
