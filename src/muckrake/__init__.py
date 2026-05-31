import importlib.util
import os
import shutil
import tempfile
from pathlib import Path


def _iter_extension_dirs() -> list[Path]:
    dirs: list[Path] = []

    raw_paths = os.getenv("MUCKRAKE_FTM_SCHEMA_PATHS")
    if raw_paths:
        for raw_path in raw_paths.split(os.pathsep):
            raw_path = raw_path.strip()
            if not raw_path:
                continue
            path = Path(raw_path).expanduser().resolve()
            if path.is_dir() and path not in dirs:
                dirs.append(path)

    cwd_dir = (Path.cwd() / "ftm_schema_ext").resolve()
    if cwd_dir.is_dir() and cwd_dir not in dirs:
        dirs.append(cwd_dir)

    return dirs


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
    extension_dirs = _iter_extension_dirs()
    if schema_dir is None or not extension_dirs:
        return

    merged_dir = Path(tempfile.mkdtemp(prefix="muckrake-ftm-model-"))
    shutil.copytree(schema_dir, merged_dir, dirs_exist_ok=True)
    for extension_dir in extension_dirs:
        for pattern in ("*.yaml", "*.yml"):
            for extension in sorted(extension_dir.glob(pattern)):
                shutil.copy2(extension, merged_dir / extension.name)

    os.environ["FTM_MODEL_PATH"] = str(merged_dir)


_configure_ftm_model_path()


def hello() -> str:
    return "Hello from muckrake!"
