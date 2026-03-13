import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, Optional
from followthemoney.statement.serialize import PackStatementWriter

from muckrake.dataset import Dataset, load_config, get_dataset_path

log = logging.getLogger(__name__)


def load_timestamps(path: Path) -> Dict[str, str]:
    """Load previous first_seen timestamps from a pack file."""
    timestamps = {}
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        log.info(f"Loading previous state from {path}...")
        try:
            with open(path, "rb") as fh:
                from followthemoney.statement.serialize import read_pack_statements
                for stmt in read_pack_statements(fh):
                    if stmt.id is not None and stmt.first_seen is not None:
                        timestamps[stmt.id] = stmt.first_seen
        except Exception as e:
            log.warning(f"Failed to load previous state: {e}")
    return timestamps


def execute_crawler(config_path: Path, ds: Dataset):
    """Dynamically load and run the crawler script for a dataset."""
    crawler_path = config_path.parent.resolve() / "crawler.py"
    if not crawler_path.exists():
        log.error(f"crawler.py not found at {crawler_path}")
        return

    # Determine the package hierarchy based on directory structure relative to datasets/
    datasets_root = Path("datasets").resolve()
    try:
        # Try to find the path relative to the datasets root
        rel_path = crawler_path.parent.relative_to(datasets_root)
        parts = ["muckrake", "crawler"] + list(rel_path.parts)
    except ValueError:
        # Fallback if crawler is not in datasets/ or we can't find the root
        parts = ["muckrake", "crawler", ds.name]

    import types
    import sys
    
    # Initialize all parent packages to ensure relative imports work.
    # We walk down the hierarchy and create virtual modules for each level.
    for i in range(1, len(parts) + 1):
        pkg_name = ".".join(parts[:i])
        if pkg_name not in sys.modules:
            mod = types.ModuleType(pkg_name)
            if i >= 2: # muckrake.crawler and below
                # Map this virtual package to the corresponding filesystem directory
                rel_parts = parts[2:i]
                fs_path = datasets_root.joinpath(*rel_parts)
                if fs_path.exists():
                    mod.__path__ = [str(fs_path)]
            
            # For packages, __package__ should be the name of the package itself.
            mod.__package__ = pkg_name
            sys.modules[pkg_name] = mod

    # The actual crawler module is a submodule of the final package
    pkg_name = ".".join(parts)
    module_name = f"{pkg_name}.crawler"
    spec = importlib.util.spec_from_file_location(module_name, str(crawler_path))
    if spec is None or spec.loader is None:
        log.error(f"Could not load crawler from {crawler_path}")
        return
    
    crawler_module = importlib.util.module_from_spec(spec)
    # Ensure the module knows its package for relative imports
    crawler_module.__package__ = pkg_name
    sys.modules[module_name] = crawler_module
    spec.loader.exec_module(crawler_module)

    if not hasattr(crawler_module, "crawl"):
        log.error(f"crawler.py in {ds.name} must define a 'crawl' function")
        return

    crawler_module.crawl(ds)


def run_crawl(config_path: Path, output: Optional[str] = None):
    """Helper to run a single crawl."""
    ds_config = load_config(config_path)
    dataset_name = ds_config.name

    if output:
        output_path = Path(output)
    else:
        output_path = get_dataset_path(dataset_name) / "statements.pack.csv"

    timestamps = load_timestamps(output_path)

    if output_path.as_posix() == "-":
        writer = PackStatementWriter(sys.stdout)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = PackStatementWriter(open(output_path, "w"))

    try:
        ds = Dataset(config_path, writer, timestamps=timestamps)
        execute_crawler(config_path, ds)
    finally:
        ds.close()
        writer.close()

    if output_path.as_posix() != "-":
        log.info(f"Crawl complete: {dataset_name} -> {output_path}")
