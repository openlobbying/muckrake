from __future__ import annotations

import json

from click.testing import CliRunner

from muckrake.cli import cli
from muckrake.entity_query import clear_query_caches


def test_add_get_and_search_cli_roundtrip(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_PUBLISHED_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))
    clear_query_caches()

    runner = CliRunner()

    add_result = runner.invoke(
        cli,
        [
            "add",
            "--schema",
            "Company",
            "--dataset",
            "test",
            "--source",
            "source-1",
            "--id-part",
            "acme-inc",
            "--property",
            "name=ACME Inc",
            "--property",
            "country=us",
        ],
    )
    assert add_result.exit_code == 0, add_result.output
    added = json.loads(add_result.output)
    entity_id = added["entity"]["id"]
    assert added["action"] == "created"

    get_result = runner.invoke(cli, ["get", entity_id])
    assert get_result.exit_code == 0, get_result.output
    fetched = json.loads(get_result.output)
    assert fetched["entity"]["properties"]["name"] == ["ACME Inc"]

    search_result = runner.invoke(cli, ["search", "ACME", "--schema", "LegalEntity"])
    assert search_result.exit_code == 0, search_result.output
    searched = json.loads(search_result.output)
    assert searched["total"] == 1
    assert searched["results"][0]["id"] == entity_id


def test_add_cli_updates_existing_entity(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_PUBLISHED_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))
    clear_query_caches()

    runner = CliRunner()
    first = runner.invoke(
        cli,
        [
            "add",
            "--schema",
            "Person",
            "--dataset",
            "test",
            "--source",
            "source-1",
            "--id",
            "person-1",
            "--property",
            "name=Alice Example",
        ],
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        cli,
        [
            "add",
            "--schema",
            "Person",
            "--dataset",
            "test",
            "--source",
            "source-2",
            "--id",
            "person-1",
            "--property",
            "name=Alice Example",
            "--property",
            "notes=Updated",
        ],
    )
    assert second.exit_code == 0, second.output
    payload = json.loads(second.output)
    assert payload["action"] == "updated"
    assert payload["entity"]["properties"]["notes"] == ["Updated"]


def test_update_cli_targets_existing_entity(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_PUBLISHED_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))
    clear_query_caches()

    runner = CliRunner()
    created = runner.invoke(
        cli,
        [
            "add",
            "--schema",
            "Person",
            "--dataset",
            "test",
            "--source",
            "source-1",
            "--id",
            "person-2",
            "--property",
            "name=Bob Example",
        ],
    )
    assert created.exit_code == 0, created.output

    updated = runner.invoke(
        cli,
        [
            "update",
            "person-2",
            "--property",
            "name=Robert Example",
            "--property",
            "notes=Updated by CLI",
        ],
    )
    assert updated.exit_code == 0, updated.output
    payload = json.loads(updated.output)
    assert payload["action"] == "updated"
    assert payload["entity"]["properties"]["name"] == ["Robert Example"]
    assert payload["entity"]["properties"]["notes"] == ["Updated by CLI"]


def test_get_cli_missing_entity_fails(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_PUBLISHED_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("MUCKRAKE_ENV_FILE", str(tmp_path / "missing.env"))
    clear_query_caches()

    runner = CliRunner()
    result = runner.invoke(cli, ["get", "missing-id"])
    assert result.exit_code != 0
