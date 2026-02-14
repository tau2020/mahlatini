"""
Claude LLM Client
==================
Communicates with Anthropic's Claude API.
"""

import json
import time
import asyncio
import logging
from typing import Optional

from anthropic import AsyncAnthropic, RateLimitError, APITimeoutError, APIError

from app.config import settings
from app.services.llm.base import BaseLLM

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]


class ClaudeLLM(BaseLLM):
    """Anthropic Claude LLM provider."""

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None

    @property
    def provider_name(self) -> str:
        return "claude"

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            if not settings.anthropic_api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. "
                    "Claude provider is unavailable."
                )
            self._client = AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=60.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> str:
        # Anthropic API: system is a top-level param, not in messages
        messages = [{"role": "user", "content": prompt}]

        client = self._get_client()
        last_error = None

        # Clamp temperature to Anthropic's range (0.0–1.0)
        temperature = min(max(temperature, 0.0), 1.0)

        kwargs = {
            "model": settings.claude_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                response = await client.messages.create(**kwargs)
                elapsed = time.monotonic() - start
                logger.info(
                    f"[claude] Response in {elapsed:.2f}s "
                    f"(model={settings.claude_model})"
                )
                return response.content[0].text.strip()

            except RateLimitError as e:
                last_error = e
                logger.warning(
                    f"[claude] Rate limit (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except APITimeoutError as e:
                last_error = e
                logger.error(
                    f"[claude] Timeout (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except APIError as e:
                logger.error(f"[claude] API error: {e.status_code} — {e.message}")
                raise
            except Exception as e:
                logger.error(f"[claude] Request failed: {e}")
                raise

        raise last_error

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict:
        raw = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=2048,
        )

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.warning(f"[claude] JSON parse failed: {raw[:200]}")
            return {}

    async def is_healthy(self) -> bool:
        try:
            client = self._get_client()
            # Simple message to verify the API key works
            response = await client.messages.create(
                model=settings.claude_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return response is not None
        except Exception as e:
            logger.warning(f"[claude] Health check failed: {e}")
            return False
