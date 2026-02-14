"""
Base LLM Interface
===================
Abstract base class that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseLLM(ABC):
    """Abstract interface for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier (e.g. 'groq', 'claude')."""
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> str:
        """Generate a text response."""
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict:
        """Generate a response and parse as JSON."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the provider API is reachable."""
        ...
