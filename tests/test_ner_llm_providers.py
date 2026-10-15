from __future__ import annotations

import pytest

from muckrake.extract.ner.engines.llm import LLMExtractor


@pytest.mark.parametrize(
    ("model", "key_var"),
    [
        ("openrouter:openai/gpt-4o-mini", "OPENROUTER_API_KEY"),
        ("anthropic:claude-haiku-5-5", "ANTHROPIC_API_KEY"),
    ],
)
def test_llm_extractor_loads_each_provider(
    monkeypatch: pytest.MonkeyPatch, model: str, key_var: str
) -> None:
    # Constructing the agent imports the provider's client library, so a locked
    # dependency that doesn't match pydantic-ai fails here, without a network call.
    monkeypatch.setenv("LLM_MODEL", model)
    monkeypatch.setenv(key_var, "test-key")
    LLMExtractor()
