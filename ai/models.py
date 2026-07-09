"""Deprecated shim — the provider layer moved to ``ai/providers/``.

Kept so that existing imports (``from ai.models import register_provider``) and
any code you wrote against the old module keep working. New code should import
from ``ai.providers`` directly.
"""
from __future__ import annotations

import warnings

from .providers import (  # noqa: F401  (re-exported for backwards compatibility)
    AnthropicProvider,
    ClaudeCLIProvider,
    CLIProvider,
    CodexCLIProvider,
    GeminiCLIProvider,
    GoogleProvider,
    LocalOpenAIProvider,
    MockProvider,
    OpenAIProvider,
    Provider,
    get_provider,
    known_providers,
    register_provider,
    register_provider_class,
)

warnings.warn(
    "ai.models is deprecated; import from ai.providers instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "Provider",
    "CLIProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "LocalOpenAIProvider",
    "GoogleProvider",
    "MockProvider",
    "ClaudeCLIProvider",
    "CodexCLIProvider",
    "GeminiCLIProvider",
    "get_provider",
    "register_provider",
    "register_provider_class",
    "known_providers",
]
