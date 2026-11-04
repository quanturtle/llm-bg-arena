"""What each OpenRouter model accepts, read from OpenRouter's public model list.

The list (`GET /api/v1/models`, no key needed) gives, per model, the request
parameters it supports and how it reasons: whether reasoning can be turned off
and which effort levels it takes. The viewer's new-match form shows a player only
the settings its model accepts. `parse_catalog` is pure; `OpenRouterCatalog`
fetches the list once per process and keeps it.
"""

import json
from typing import Protocol, get_args

import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

from boardgames.core import ArenaError
from boardgames.llm.model import ReasoningEffort
from boardgames.llm.openrouter_model import DEFAULT_BASE_URL

CATALOG_TIMEOUT_SECONDS = 20.0
EFFORTS_LEAST_FIRST: tuple[ReasoningEffort, ...] = get_args(ReasoningEffort.__value__)


class CatalogUnavailableError(ArenaError):
    """OpenRouter's model list could not be fetched or read."""


class ReasoningSupport(BaseModel):
    """How a model reasons; `efforts` is empty when it takes no effort level."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_mandatory: bool
    efforts: list[ReasoningEffort]
    default_effort: ReasoningEffort | None


class ModelCapabilities(BaseModel):
    """A model's accepted request parameters; `reasoning` is None if it cannot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    parameters: list[str]
    reasoning: ReasoningSupport | None
    max_output_tokens: int | None
    default_temperature: float | None


class ModelCatalog(Protocol):
    async def lookup(self, model_id: str) -> ModelCapabilities | None:
        """The model's capabilities; None for ids OpenRouter does not list."""
        ...


class ReasoningPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mandatory: bool = False
    supported_efforts: list[str] = []
    default_effort: str | None = None


class TopProviderPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_completion_tokens: int | None = None


class ModelPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = ""
    supported_parameters: list[str] = []
    reasoning: ReasoningPayload | None = None
    top_provider: TopProviderPayload | None = None
    default_parameters: dict[str, object] | None = None


class ModelListPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[ModelPayload]


class OpenRouterCatalog:
    """OpenRouter's model list, fetched on first use and kept for the process."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._url = f"{base_url}/models"
        self._models: dict[str, ModelCapabilities] | None = None
        return

    async def lookup(self, model_id: str) -> ModelCapabilities | None:
        if self._models is None:
            self._models = await self._fetch()
        return self._models.get(model_id)

    async def _fetch(self) -> dict[str, ModelCapabilities]:
        try:
            async with httpx2.AsyncClient(timeout=CATALOG_TIMEOUT_SECONDS) as client:
                response = await client.get(self._url)
                response.raise_for_status()
                payload = response.json()
        except (httpx2.HTTPError, json.JSONDecodeError) as error:
            raise CatalogUnavailableError(
                f"cannot read OpenRouter's model list: {error}"
            ) from error
        return parse_catalog(payload)


def parse_catalog(payload: object) -> dict[str, ModelCapabilities]:
    """Capabilities by model id from the body of OpenRouter's model list."""
    try:
        listing = ModelListPayload.model_validate(payload)
    except ValidationError as error:
        raise CatalogUnavailableError(
            f"OpenRouter's model list has an unexpected shape: {error}"
        ) from error
    return {model.id: capabilities_of(model) for model in listing.data}


def capabilities_of(model: ModelPayload) -> ModelCapabilities:
    """One listed model as capabilities; unknown effort levels drop out."""
    temperature = (model.default_parameters or {}).get("temperature")
    provider = model.top_provider or TopProviderPayload()
    reasoning = None if model.reasoning is None else reasoning_of(model.reasoning)
    return ModelCapabilities(
        id=model.id,
        name=model.name or model.id,
        parameters=sorted(model.supported_parameters),
        reasoning=reasoning,
        max_output_tokens=provider.max_completion_tokens,
        default_temperature=(
            float(temperature) if isinstance(temperature, int | float) else None
        ),
    )


def reasoning_of(reasoning: ReasoningPayload) -> ReasoningSupport:
    """Reasoning support with effort levels least first; "none" is the off switch."""
    return ReasoningSupport(
        is_mandatory=reasoning.mandatory,
        efforts=[e for e in EFFORTS_LEAST_FIRST if e in reasoning.supported_efforts],
        default_effort=next(
            (e for e in EFFORTS_LEAST_FIRST if e == reasoning.default_effort), None
        ),
    )
