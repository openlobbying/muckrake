import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from lxml.html import HtmlElement
from datapatch import get_lookups, Lookup
from followthemoney import Dataset as FTMDataset
from followthemoney.statement.entity import StatementEntity
from nomenklatura.cache import Cache
from nomenklatura.db import get_engine, get_metadata

from org_id import make_hashed_id, make_org_id

from muckrake.extract.fetch import fetch_file, fetch_json, fetch_html, fetch_text
from muckrake.settings import DATA_PATH, SQL_URI


def load_raw_config(path: Path) -> Dict[str, Any]:
    import yaml

    with path.open("r") as fh:
        return yaml.safe_load(fh) or {}


def get_dataset_config(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("dataset", data)


def get_dataset_path(name: str) -> Path:
    return DATA_PATH / "datasets" / name


def clear_dataset(name: str):
    """Delete all data associated with a dataset."""
    path = get_dataset_path(name)
    if path.exists():
        logging.getLogger(__name__).info(f"Clearing dataset data: {name}")
        shutil.rmtree(path)


def load_config(path: Path) -> FTMDataset:
    """Load a dataset configuration from a file path."""
    return FTMDataset.make(get_dataset_config(load_raw_config(path)))


class Dataset:
    """A runner context for a specific data source."""

    def __init__(
        self,
        config_path: Path,
        writer: Any,
        timestamps: Optional[Dict[str, str]] = None,
    ):
        self._data = load_raw_config(config_path)
        config = get_dataset_config(self._data)
        self.ftm = FTMDataset.make(config)
        self.name = self.ftm.name
        self.prefix = config.get("prefix", self.name)

        self.writer = writer
        self.timestamps = timestamps or {}
        self.run_time = datetime.utcnow().isoformat()

        # Standardize where resources are kept
        self.data_path = get_dataset_path(self.name)
        self.resources_path = self.data_path / "resources"
        self.log = logging.getLogger(self.name)
        self._cache: Optional[Cache] = None

    @property
    def cache(self) -> Cache:
        if self._cache is None:
            self._cache = Cache(
                get_engine(SQL_URI), get_metadata(), self.ftm, create=True
            )
        return self._cache

    @property
    def lookups(self) -> Dict[str, Lookup]:
        """Load datapatch lookups from config (cached after first access)."""
        if not hasattr(self, "_lookups_cache"):
            config = self._data.get("lookups", {})
            self._lookups_cache: Dict[str, Lookup] = get_lookups(config)
        return self._lookups_cache

    def lookup(self, lookup_name: str, value: Any):
        """Convenience method to apply a lookup, returning the result object or None."""
        if lookup_name not in self.lookups:
            return None
        return self.lookups[lookup_name].match(value)

    def make(self, schema: str) -> StatementEntity:
        """Create an entity tied to this dataset."""
        return StatementEntity(self.ftm, {"schema": schema})

    def make_id(
        self, *parts: Any, reg_nr: Optional[Any] = None, register: Optional[str] = None
    ) -> str:
        """Create a stable ID, preferring a structured org-id if reg_nr is provided."""
        if reg_nr:
            if not register:
                raise ValueError(
                    "Mapping an org-id requires a 'register' (e.g. 'GB-COH')"
                )
            org_id = make_org_id(reg_nr, register=register)
            if org_id:
                return org_id

        return make_hashed_id(self.prefix, *parts)

    def emit(self, entity: StatementEntity):
        """Write entity statements to the output stream with timestamps."""
        for stmt in entity.statements:
            stmt_id = stmt.id
            if stmt_id:
                stmt.first_seen = self.timestamps.get(stmt_id, self.run_time)
            else:
                stmt.first_seen = self.run_time
            stmt.last_seen = self.run_time
            self.writer.write(stmt)

    def fetch_resource(self, name: str, url: str, **kwargs: Any):
        """Standard file downloader for datasets."""

        try:
            return fetch_file(url, name, data_path=self.resources_path, **kwargs)
        except Exception as e:
            self.log.error(f"Failed to fetch resource {url}: {e}")
            raise

    def fetch_text(
        self, url: str, cache_days: Optional[int] = None, **kwargs: Any
    ) -> Optional[str]:
        """Fetch text from a URL, optionally cached."""
        return fetch_text(url, cache=self.cache, cache_days=cache_days, **kwargs)

    def fetch_json(
        self, url: str, cache_days: Optional[int] = None, **kwargs: Any
    ) -> Any:
        """Fetch JSON from a URL, optionally cached."""
        return fetch_json(url, cache=self.cache, cache_days=cache_days, **kwargs)

    def fetch_html(
        self, url: str, cache_days: Optional[int] = None, **kwargs: Any
    ) -> HtmlElement:
        """Fetch HTML from a URL, optionally cached."""
        return fetch_html(url, cache=self.cache, cache_days=cache_days, **kwargs)

    def close(self) -> None:
        """Close the dataset and persist any cached data."""
        if self._cache is not None:
            self._cache.close()


def find_datasets(name: Optional[str] = None) -> List[Path]:
    """Find dataset config files in the datasets/ directory.

    Args:
        name: Dataset name as defined in config (e.g., 'gb_political_finance').
              If None, finds all datasets recursively.
    """
    datasets_root = Path("datasets")

    # Find all config files recursively
    configs = []
    for ext in ["yml", "yaml"]:
        configs.extend(datasets_root.glob(f"**/config.{ext}"))

    if name:
        # Search through all configs to find the one with matching name
        for config in configs:
            try:
                ds = load_config(config)
                if ds.name == name:
                    return [config]
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"Failed to load config {config}: {e}"
                )
                continue
        return []

    return sorted(list(set(configs)))


def list_datasets() -> List[FTMDataset]:
    """Load all dataset configurations."""
    return [load_config(p) for p in find_datasets()]


def list_dataset_names() -> List[str]:
    """Get names of all datasets."""
    return [ds.name for ds in list_datasets()]
