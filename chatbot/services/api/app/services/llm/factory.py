"""
LLM Factory
=============
Creates and caches LLM provider instances.
"""

import logging

from app.config import settings
from app.services.llm.base import BaseLLM

logger = logging.getLogger(__name__)

_instances: dict[str, BaseLLM] = {}


def get_llm(provider: str = None) -> BaseLLM:
    """
    Get an LLM provider instance by name.

    Args:
        provider: "groq" or "claude". Defaults to settings.default_provider.

    Returns:
        BaseLLM instance (cached singleton per provider).

    Raises:
        ValueError: If provider is unknown.
    """
    if provider is None:
        provider = settings.default_provider

    provider = provider.lower().strip()

    if provider in _instances:
        return _instances[provider]

    if provider == "groq":
        from app.services.llm.groq_client import GroqLLM
        instance = GroqLLM()

    elif provider == "claude":
        from app.services.llm.claude_client import ClaudeLLM
        instance = ClaudeLLM()

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: 'groq', 'claude'."
        )

    _instances[provider] = instance
    logger.info(f"Initialised LLM provider: {provider}")
    return instance
