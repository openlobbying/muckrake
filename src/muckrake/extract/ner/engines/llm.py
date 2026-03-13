import os
from pathlib import Path
from typing import Any

from followthemoney import model
from pydantic import BaseModel, Field

from muckrake.logging import configure_logging

from .base import Extractor, RecoverableExtractionError
from .llm_prompt import DEFAULT_SYSTEM_PROMPT, build_user_prompt


def _get_system_prompt() -> str:
    prompt_path = os.getenv("NER_LLM_PROMPT_FILE")
    if prompt_path:
        path = Path(prompt_path)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return DEFAULT_SYSTEM_PROMPT


class LLMEntity(BaseModel):
    key: str | None = None
    schema_: str = Field(alias="schema")
    properties: dict[str, list[str]] = Field(default_factory=dict)


class LLMExtractor(Extractor):
    name = "llm"

    def __init__(self) -> None:
        configure_logging(enable_logfire=True)

        model_name = os.getenv("LLM_MODEL")
        if not model_name:
            raise RuntimeError("LLM_MODEL is not set")

        from pydantic_ai import Agent
        from pydantic_ai import ModelRetry

        model_name = self._normalize_model_name(model_name)

        self._agent = Agent(
            model_name,
            output_type=list[LLMEntity],
            system_prompt=_get_system_prompt(),
            output_retries=3,
        )

        @self._agent.output_validator
        def _validate_output(entities: list[LLMEntity]) -> list[LLMEntity]:
            try:
                self._validate_extraction_output(entities)
            except ValueError as exc:
                raise ModelRetry(str(exc)) from exc
            return entities

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        return model_name.strip()

    @staticmethod
    def _validate_extraction_output(entities: list[LLMEntity]) -> None:
        key_to_schema: dict[str, str] = {}

        if not entities:
            raise ValueError(
                "No entities extracted. Return at least one entity when text contains named actors."
            )

        for entity in entities:
            if entity.key:
                key_to_schema[entity.key] = entity.schema_

            schema_name = entity.schema_
            schema = model.get(schema_name)
            if schema is None:
                raise ValueError(f"Unknown schema '{schema_name}'.")

            if not entity.properties:
                raise ValueError(f"Entity '{schema_name}' has no properties.")

            for prop_name, values in entity.properties.items():
                if prop_name not in schema.properties:
                    available = ", ".join(sorted(schema.properties.keys()))
                    raise ValueError(
                        f"Property '{prop_name}' is not valid for entity '{schema_name}'. "
                        f"Available properties: [{available}]"
                    )

                if not isinstance(values, list) or not values:
                    raise ValueError(
                        f"Property '{prop_name}' on '{schema_name}' must be a non-empty list of strings."
                    )

                prop = schema.get(prop_name)
                if prop is None:
                    available = ", ".join(sorted(schema.properties.keys()))
                    raise ValueError(
                        f"Property '{prop_name}' is not valid for entity '{schema_name}'. "
                        f"Available properties: [{available}]"
                    )
                assert prop is not None
                for value in values:
                    if not isinstance(value, str):
                        raise ValueError(
                            f"Property '{prop_name}' on '{schema_name}' must contain strings only."
                        )

                    if value.startswith("$ref:"):
                        if prop.type.name != "entity":
                            raise ValueError(
                                f"Property '{prop_name}' on '{schema_name}' cannot use $ref values."
                            )
                        continue

                    cleaned = prop.type.clean(value)
                    if cleaned is None:
                        raise ValueError(
                            f"Invalid value '{value}' for property '{prop_name}' on '{schema_name}'."
                        )

        for entity in entities:
            schema = model.get(entity.schema_)
            if schema is None:
                raise ValueError(f"Unknown schema '{entity.schema_}'.")
            for prop_name, values in entity.properties.items():
                prop = schema.get(prop_name)
                if prop is None:
                    raise ValueError(
                        f"Property '{prop_name}' is not valid for entity '{entity.schema_}'."
                    )
                if prop.type.name != "entity":
                    continue

                for value in values:
                    if not value.startswith("$ref:"):
                        continue
                    ref_key = value[5:]
                    ref_schema_name = key_to_schema.get(ref_key)
                    if ref_schema_name is None:
                        raise ValueError(
                            f"Unknown entity reference key '{ref_key}' for property '{prop_name}'."
                        )
                    ref_schema = model.get(ref_schema_name)
                    if ref_schema is None:
                        raise ValueError(
                            f"Unknown schema '{ref_schema_name}' for ref '{ref_key}'."
                        )
                    if prop.range is not None and not ref_schema.is_a(prop.range):
                        raise ValueError(
                            f"Reference '$ref:{ref_key}' has schema '{ref_schema_name}', "
                            f"but property '{entity.schema_}.{prop_name}' expects '{prop.range.name}'."
                        )

    def extract(self, text: str) -> list[dict[str, Any]]:
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        try:
            result = self._agent.run_sync(build_user_prompt(text))
        except UnexpectedModelBehavior as exc:
            raise RecoverableExtractionError(str(exc)) from exc
        return [e.model_dump(exclude_none=True, by_alias=True) for e in result.output]
