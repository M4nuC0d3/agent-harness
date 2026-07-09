"""Provider adapters, one module per vendor, behind a single interface.

Two billing paths:

  API key      anthropic | openai | local | google      billed per token
  Subscription claude_cli | codex_cli | gemini_cli      draws on your plan
  Offline      mock                                     free, no network

Pick per role in config.yaml (``provider:``). Add your own with
``register_provider("name", MyProvider())``.

All vendor SDK imports are lazy, so the harness loads and runs (with the mock
provider) even if you have not installed any vendor SDK.
"""
from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import (
    LLMResponse,
    Provider,
    get_provider,
    known_providers,
    register_provider,
    register_provider_class,
)
from .cli import ClaudeCLIProvider, CLIProvider, CodexCLIProvider, GeminiCLIProvider
from .google import GoogleProvider
from .mock import MockProvider
from .openai import LocalOpenAIProvider, OpenAIProvider

for _cls in (
    AnthropicProvider,
    OpenAIProvider,
    LocalOpenAIProvider,
    GoogleProvider,
    MockProvider,
    ClaudeCLIProvider,
    CodexCLIProvider,
    GeminiCLIProvider,
):
    register_provider_class(_cls.name, _cls)

__all__ = [
    "Provider",
    "CLIProvider",
    "LLMResponse",
    "get_provider",
    "register_provider",
    "register_provider_class",
    "known_providers",
    "AnthropicProvider",
    "OpenAIProvider",
    "LocalOpenAIProvider",
    "GoogleProvider",
    "MockProvider",
    "ClaudeCLIProvider",
    "CodexCLIProvider",
    "GeminiCLIProvider",
]
