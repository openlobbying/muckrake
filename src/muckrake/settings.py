import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from muckrake.env import find_env_file, load_env_file

# Base directory of the project
BASE_PATH = Path(__file__).parent.parent.parent


@dataclass(frozen=True)
class EnvVar:
    name: str
    default: str
    description: str


# Every environment variable muckrake reads, directly or through a library it
# configures. docs/env.md is generated from this list (scripts/gen_docs.py), and
# tests/test_docs_current.py fails if a variable read in src/ is missing here.
ENV_VARS: list[EnvVar] = [
    EnvVar(
        "MUCKRAKE_DATABASE_URL",
        "`sqlite:///data/muckrake.db`",
        "Working database: crawl runs, loaded statements, resolver, NER candidates, "
        "HTTP cache, releases. A `postgresql://` URL selects Postgres.",
    ),
    EnvVar(
        "MUCKRAKE_PUBLISHED_DATABASE_URL",
        "the working database URL",
        "Read-only serving database that `release-publish` writes. **Must differ from "
        "the working database**: `release-publish` refuses to run otherwise.",
    ),
    EnvVar(
        "MUCKRAKE_DATA_PATH",
        "`data`",
        "Directory for the default SQLite database, dataset workspaces "
        "(`<path>/datasets/<name>/`) and the LevelDB store.",
    ),
    EnvVar(
        "MUCKRAKE_ARTIFACT_PATH",
        "`<MUCKRAKE_DATA_PATH>/artifacts`",
        "Immutable crawl and release artifacts.",
    ),
    EnvVar(
        "MUCKRAKE_DATASET_PATHS",
        "unset",
        "Extra dataset roots, separated by the OS path separator (`:` on Unix). "
        "`./datasets/` in the current directory is always searched.",
    ),
    EnvVar(
        "MUCKRAKE_FTM_SCHEMA_PATHS",
        "unset",
        "FollowTheMoney schema extension directories, separated by the OS path "
        "separator. `./ftm_schema_ext/` in the current directory is always used if present.",
    ),
    EnvVar(
        "MUCKRAKE_ENV_FILE",
        "nearest `.env` from the current directory upward",
        "Explicit `.env` file to load.",
    ),
    EnvVar(
        "MUCKRAKE_HTTP_MIN_INTERVAL",
        "`0`",
        "Minimum seconds between HTTP requests to the same host (politeness rate limit).",
    ),
    EnvVar(
        "MUCKRAKE_PROFILE_URL",
        "unset",
        "Link template for entities in the `dedupe` review TUI, with `%s` for the "
        "entity ID, e.g. `https://example.org/entity/%s`. Unset shows no links.",
    ),
    EnvVar(
        "FTM_MODEL_PATH",
        "set by muckrake",
        "FollowTheMoney model directory. muckrake sets it to the upstream model merged "
        "with any schema extensions; set it only to override that.",
    ),
    EnvVar(
        "LLM_MODEL",
        "unset",
        "Model for `ner-extract --extractor llm`, with its provider prefix: "
        "`openrouter:<model>` or `anthropic:<model>`.",
    ),
    EnvVar("OPENROUTER_API_KEY", "unset", "API key for `openrouter:` models."),
    EnvVar("ANTHROPIC_API_KEY", "unset", "API key for `anthropic:` models."),
    EnvVar(
        "NER_LLM_PROMPT_FILE",
        "built-in prompt",
        "File whose text replaces the LLM extractor's system prompt.",
    ),
    EnvVar("LOGFIRE_TOKEN", "unset", "Send LLM extraction traces to Logfire when set."),
    EnvVar(
        "ENVIRONMENT",
        "`development`",
        "Environment name reported to Logfire. `production` skips loading `.env`.",
    ),
]


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


def ensure_sqlite_dirs(*uris: str) -> None:
    """Create the parent directory of each SQLite database file.

    SQLite creates a missing database file but not its directory, so without
    this a fresh checkout (no ``data/``) fails with "unable to open database file".
    """
    for uri in uris:
        url = make_url(uri)
        database = url.database
        if url.get_backend_name() == "sqlite" and database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)


DATA_PATH = Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))
ARTIFACT_PATH = Path(os.getenv("MUCKRAKE_ARTIFACT_PATH", DATA_PATH / "artifacts"))
SQL_URI: str = get_working_sql_uri()
PUBLISHED_SQL_URI: str = get_published_sql_uri()
PROFILE_URL: str | None = os.getenv("MUCKRAKE_PROFILE_URL") or None

LEVEL_PATH = DATA_PATH / "leveldb"
