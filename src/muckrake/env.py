import os
from pathlib import Path


def find_env_file(
    start: Path | None = None, fallback_paths: list[Path] | None = None
) -> Path | None:
    explicit = os.getenv("MUCKRAKE_ENV_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None

    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.exists():
            return candidate

    for candidate in fallback_paths or []:
        if candidate.exists():
            return candidate

    return None


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value

    return values


def load_env_file(path: Path) -> None:
    for key, value in read_env_file(path).items():
        os.environ.setdefault(key, value)
