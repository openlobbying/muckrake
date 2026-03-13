from collections.abc import Callable

from .base import Extractor
from .delimited import DelimitedExtractor


def _load_delimiter() -> Extractor:
    return DelimitedExtractor()


def _load_llm() -> Extractor:
    from .llm import LLMExtractor

    return LLMExtractor()


EXTRACTORS: dict[str, Callable[[], Extractor]] = {
    "delimiter": _load_delimiter,
    "llm": _load_llm,
}


def get_extractor(name: str) -> Extractor:
    factory = EXTRACTORS.get(name)
    if factory is None:
        available = ", ".join(sorted(EXTRACTORS.keys()))
        raise ValueError(f"Unknown extractor '{name}'. Available: {available}")
    return factory()


def list_extractors() -> list[str]:
    return sorted(EXTRACTORS.keys())
