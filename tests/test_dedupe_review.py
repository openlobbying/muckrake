from __future__ import annotations

from muckrake.dedupe.review import _resolve_user_label


def test_judgement_user_label_has_no_built_in_prefix():
    assert _resolve_user_label("u1", None, None) == "u1"
    assert _resolve_user_label("u1", " Ada ", None) == "u1:Ada"


def test_judgement_user_label_uses_caller_prefix():
    assert _resolve_user_label("u1", "Ada", "myapp") == "myapp:u1:Ada"
    assert _resolve_user_label("u1", "", "myapp") == "myapp:u1"
