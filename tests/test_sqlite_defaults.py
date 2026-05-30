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
