import importlib.util
import os
import shutil
import tempfile
from pathlib import Path


def _find_followthemoney_schema_dir() -> Path | None:
    spec = importlib.util.find_spec("followthemoney")
    if spec is None or spec.origin is None:
        return None
    schema_dir = Path(spec.origin).resolve().parent / "schema"
    if not schema_dir.is_dir():
        return None
    return schema_dir


def _configure_ftm_model_path() -> None:
    if os.getenv("FTM_MODEL_PATH"):
        return

    schema_dir = _find_followthemoney_schema_dir()
    extensions_dir = Path(__file__).resolve().parent / "ftm_schema_ext"
    if schema_dir is None or not extensions_dir.is_dir():
        return

    merged_dir = Path(tempfile.mkdtemp(prefix="muckrake-ftm-model-"))
    shutil.copytree(schema_dir, merged_dir, dirs_exist_ok=True)
    for pattern in ("*.yaml", "*.yml"):
        for extension in sorted(extensions_dir.glob(pattern)):
            shutil.copy2(extension, merged_dir / extension.name)

    os.environ["FTM_MODEL_PATH"] = str(merged_dir)


_configure_ftm_model_path()


def hello() -> str:
    return "Hello from muckrake!"
