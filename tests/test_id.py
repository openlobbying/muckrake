from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from muckrake.dataset import Dataset
from muckrake.id import is_org_id, make_hashed_id, make_org_id


def _dataset(tmp_path: Path, *, prefix: str = "tid") -> Dataset:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump({"name": "test_ids", "title": "Test IDs", "prefix": prefix})
    )
    return Dataset(config_path, object())


def test_make_hashed_id_is_deterministic():
    assert make_hashed_id("pre", "a", "b") == make_hashed_id("pre", "a", "b")


def test_make_hashed_id_depends_on_prefix_and_parts():
    base = make_hashed_id("pre", "a")
    assert make_hashed_id("other", "a") != base
    assert make_hashed_id("pre", "a", "b") != base


def test_make_hashed_id_ignores_none_parts():
    assert make_hashed_id("pre", "a", None, "b") == make_hashed_id("pre", "a", "b")


def test_make_org_id_returns_gb_coh_identifier():
    assert make_org_id("01234567", register="GB-COH") == "GB-COH-01234567"


def test_make_org_id_normalises_whitespace_and_case():
    assert make_org_id(" 01234567 ", register="gb-coh") == "GB-COH-01234567"


def test_make_org_id_unknown_register_is_fallback_identifier():
    # Unknown registers do not fail; org-id emits a scheme-prefixed fallback id
    # (with a UserWarning). Verified behaviour, not a guess.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert make_org_id("12345", register="ZZ-NOPE") == "ZZ-NOPE-12345"


def test_make_org_id_empty_reg_nr_is_none():
    assert make_org_id("", register="GB-COH") is None


def test_is_org_id_recognises_org_ids_not_hashes():
    assert is_org_id("GB-COH-01234567") is True
    assert is_org_id(make_hashed_id("pre", "a")) is False


def test_dataset_make_id_uses_org_id_when_reg_nr_given(tmp_path):
    dataset = _dataset(tmp_path)
    got = dataset.make_id("acme", reg_nr="01234567", register="GB-COH")
    assert got == "GB-COH-01234567"


def test_dataset_make_id_hashes_when_no_reg_nr(tmp_path):
    got = _dataset(tmp_path, prefix="tid").make_id("acme")
    assert got == make_hashed_id("tid", "acme")
    # Stable across independent Dataset instances sharing the same prefix.
    assert got == _dataset(tmp_path, prefix="tid").make_id("acme")


def test_dataset_make_id_requires_register_with_reg_nr(tmp_path):
    dataset = _dataset(tmp_path)
    with pytest.raises(ValueError, match="register"):
        dataset.make_id("acme", reg_nr="01234567")


def test_org_id_registry_default_is_not_cached():
    # Pins current behaviour: the installed org-id rebuilds the Registry from the
    # bundled JSON on every Registry.default() call rather than sharing a cached
    # instance. Known finding (docs#38): the cache fix awaits org-id v0.1.1
    # (org-id#2 / muckrake#21); until then this is a hot-path cost at scale.
    from org_id import Registry

    assert Registry.default() is not Registry.default()
