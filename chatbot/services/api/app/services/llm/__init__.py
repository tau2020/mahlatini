"""
LLM Service Package
=====================
Provides multi-provider LLM access with backward-compatible module-level functions.

Usage (new — provider-aware):
    from app.services.llm import get_llm
    llm = get_llm("claude")
    reply = await llm.generate(prompt, system_prompt)

Usage (legacy — defaults to Groq):
    from app.services.llm import generate, generate_json
    reply = await generate(prompt, system_prompt)
"""

import re
import logging
from typing import Optional, AsyncGenerator

from app.config import settings
from app.services.llm.base import BaseLLM
from app.services.llm.factory import get_llm

logger = logging.getLogger(__name__)

__all__ = [
    "BaseLLM",
    "get_llm",
    "generate",
    "generate_stream",
    "generate_json",
    "compress_response",
    "is_healthy",
]


# ─── Backward-compatible module-level functions ──────────────
# These default to the configured provider (Groq unless overridden).
# Existing code that imports `from app.services.llm import generate`
# will continue to work without changes.


async def generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
) -> str:
    """Generate using the default provider."""
    llm = get_llm()
    return await llm.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )


async def generate_stream(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """Stream using the default provider (Groq only)."""
    from app.services.llm.groq_client import GroqLLM
    llm = get_llm()
    if isinstance(llm, GroqLLM):
        async for token in llm.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token
    else:
        # Non-streaming fallback for providers that don't support streaming
        result = await llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield result


async def generate_json(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.1,
) -> dict:
    """Generate JSON using the default provider."""
    llm = get_llm()
    return await llm.generate_json(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
    )


async def compress_response(
    response: str,
    sentence_limit: int = 4,
    provider: str = None,
) -> str:
    """
    Post-process a chat response for conversational brevity.

    If the response exceeds the sentence limit or contains
    bullet/numbered lists, compresses it via a second LLM call.
    """
    if not settings.llm_compress_enabled:
        return response

    sentences = re.split(r'(?<=[.!?])\s+', response.strip())
    sentences = [s for s in sentences if len(s) > 5]
    sentence_count = len(sentences)

    has_bullets = bool(re.search(r'^\s*[-*•]\s', response, re.MULTILINE))
    has_numbered = bool(re.search(r'^\s*\d+[.)]\s', response, re.MULTILINE))
    has_headers = bool(re.search(r'^\s*#{1,3}\s', response, re.MULTILINE))

    needs_compression = (
        sentence_count > sentence_limit
        or has_bullets
        or has_numbered
        or has_headers
    )

    if not needs_compression:
        return response

    logger.info(
        f"Compressing response: {sentence_count} sentences, "
        f"bullets={has_bullets}, numbered={has_numbered}"
    )

    llm = get_llm(provider)
    compressed = await llm.generate(
        prompt=(
            "Rewrite this travel concierge reply in 1-3 natural conversational sentences. "
            "No bullet points, no lists, no headers. Keep it warm and direct. "
            "Preserve any follow-up question if there is one. Do not add new information.\n\n"
            f"ORIGINAL:\n{response}"
        ),
        system_prompt="You shorten text into brief, natural chat messages. Output only the rewritten text.",
        temperature=0.5,
        max_tokens=200,
    )

    return compressed


async def is_healthy() -> bool:
    """Check if the default provider is healthy."""
    llm = get_llm()
    return await llm.is_healthy()
