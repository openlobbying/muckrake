from __future__ import annotations

import importlib


def test_settings_default_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("MUCKRAKE_DATABASE_URL", raising=False)
    monkeypatch.delenv("MUCKRAKE_PUBLISHED_DATABASE_URL", raising=False)
    monkeypatch.setenv("MUCKRAKE_DATA_PATH", str(tmp_path / "data"))
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))

    import muckrake.settings as settings

    importlib.reload(settings)

    assert settings.SQL_URI.startswith("sqlite:///")
    assert settings.PUBLISHED_SQL_URI == settings.SQL_URI
    assert settings.SQL_URI.endswith("/data/muckrake.db")


def test_settings_keep_explicit_postgres(monkeypatch, tmp_path):
    monkeypatch.setenv("MUCKRAKE_DATA_PATH", str(tmp_path / "data"))
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv(
        "MUCKRAKE_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/muckrake",
    )
    monkeypatch.setenv(
        "MUCKRAKE_PUBLISHED_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/muckrake_published",
    )

    import muckrake.settings as settings

    importlib.reload(settings)

    assert settings.SQL_URI == "postgresql+psycopg://user:pass@localhost:5432/muckrake"
    assert (
        settings.PUBLISHED_SQL_URI
        == "postgresql+psycopg://user:pass@localhost:5432/muckrake_published"
    )


def test_ensure_sqlite_dirs_creates_parent_dirs(tmp_path):
    from muckrake.settings import ensure_sqlite_dirs

    db_path = tmp_path / "fresh" / "data" / "muckrake.db"
    ensure_sqlite_dirs(
        f"sqlite:///{db_path.as_posix()}",
        "sqlite://",
        "postgresql+psycopg://user:pass@localhost:5432/muckrake",
    )
    assert db_path.parent.is_dir()


def test_cli_works_without_a_data_dir(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from muckrake.cli import cli

    data_path = tmp_path / "no-data-yet"
    monkeypatch.delenv("MUCKRAKE_DATABASE_URL", raising=False)
    monkeypatch.setenv("MUCKRAKE_DATA_PATH", str(data_path))

    # The working DB defaults to <MUCKRAKE_DATA_PATH>/muckrake.db; every command
    # creates its directory first, so a fresh checkout without data/ works.
    result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0, result.output
    assert data_path.is_dir()
