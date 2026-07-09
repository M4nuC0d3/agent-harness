"""Provider interface and registry.

Every provider implements ``async def complete(...) -> LLMResponse``, so the
orchestrator never knows (or cares) which vendor is behind a role. That is what
makes ``provider:`` in config.yaml a one-line switch.

``get_provider(spec)`` returns a cached instance for a ModelSpec's provider name.
Concrete providers live in sibling modules and are registered in __init__.py.
"""
from __future__ import annotations

from typing import Type

from ..schemas import LLMResponse, ModelSpec


class Provider:
    """Base class. Subclass this to plug in a vendor, a router, or a proxy."""

    name = "base"

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        raise NotImplementedError


# name -> class (lazily instantiated) and name -> live instance (cached)
_PROVIDER_CLASSES: dict[str, Type[Provider]] = {}
_PROVIDERS: dict[str, Provider] = {}


def register_provider_class(name: str, cls: Type[Provider]) -> None:
    """Register a provider *class*; instantiated on first use."""
    _PROVIDER_CLASSES[name] = cls


def register_provider(name: str, provider: Provider) -> None:
    """Plug in a custom provider *instance* at runtime (Azure, Bedrock, …)."""
    _PROVIDERS[name] = provider
    _PROVIDER_CLASSES[name] = type(provider)


def get_provider(spec: ModelSpec) -> Provider:
    """Return a cached provider instance for the given spec's provider name."""
    key = spec.provider
    if key not in _PROVIDERS:
        if key not in _PROVIDER_CLASSES:
            raise ValueError(
                f"Unknown provider '{key}'. Known: {sorted(_PROVIDER_CLASSES)}. "
                "Register your own with register_provider()."
            )
        _PROVIDERS[key] = _PROVIDER_CLASSES[key]()
    return _PROVIDERS[key]


def known_providers() -> list[str]:
    return sorted(_PROVIDER_CLASSES)


__all__ = [
    "Provider",
    "LLMResponse",
    "get_provider",
    "register_provider",
    "register_provider_class",
    "known_providers",
]
