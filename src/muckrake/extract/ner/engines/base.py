from abc import ABC, abstractmethod
from typing import Any


class RecoverableExtractionError(Exception):
    pass


class Extractor(ABC):
    name: str

    @abstractmethod
    def extract(self, text: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def extract_async(self, text: str) -> list[dict[str, Any]]:
        """Extract without blocking the event loop; I/O-bound extractors override this."""
        return self.extract(text)
