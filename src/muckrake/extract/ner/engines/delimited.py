import re
from typing import Any

from .base import Extractor


class DelimitedExtractor(Extractor):
    name = "delimiter"

    @staticmethod
    def _normalize(segment: str) -> str:
        return " ".join(segment.strip().split())

    def extract(self, text: str) -> list[dict[str, Any]]:
        parts = re.split(r"[;,]", text)
        entities: list[dict[str, Any]] = []
        for part in parts:
            seg = self._normalize(part)
            if len(seg) < 3:
                continue
            entities.append(
                {
                    "schema": "LegalEntity",
                    "properties": {
                        "name": [seg],
                    },
                }
            )

        unique_entities: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for entity in entities:
            name = entity["properties"]["name"][0]
            if name in seen_names:
                continue
            seen_names.add(name)
            unique_entities.append(entity)

        return unique_entities
