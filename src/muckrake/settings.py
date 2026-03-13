import os
from pathlib import Path

# Base directory of the project
BASE_PATH = Path(__file__).parent.parent.parent
DATA_PATH = Path(os.getenv("MUCKRAKE_DATA_PATH", "data"))
DATABASE_URL = os.getenv("MUCKRAKE_DATABASE_URL")

# Database paths
SQL_PATH = DATA_PATH / "muckrake.db"
SQL_URI = DATABASE_URL or f"sqlite:///{SQL_PATH.as_posix()}"
RESOLVER_PATH = DATA_PATH / "resolver.json"  # Legacy if used, but usually we use SQL

# LevelDB path for xref/dedupe
LEVEL_PATH = DATA_PATH / "leveldb"

# Schemata configuration
ACTOR_SCHEMATA = {"LegalEntity", "Person", "Organization", "Company", "PublicBody"}

# Search configuration
SEARCH_LIMIT = 25
