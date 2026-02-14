"""
Groq LLM Client
=================
Communicates with Groq Cloud API for fast LLM inference.
"""

import json
import time
import asyncio
import logging
from typing import Optional, AsyncGenerator

from groq import AsyncGroq, APIError, APITimeoutError, RateLimitError

from app.config import settings
from app.services.llm.base import BaseLLM

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]


class GroqLLM(BaseLLM):
    """Groq Cloud LLM provider."""

    def __init__(self):
        self._client: Optional[AsyncGroq] = None

    @property
    def provider_name(self) -> str:
        return "groq"

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(
                api_key=settings.groq_api_key,
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                response = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                )
                elapsed = time.monotonic() - start
                logger.info(
                    f"[groq] Response in {elapsed:.2f}s "
                    f"(model={settings.groq_model})"
                )
                return response.choices[0].message.content.strip()

            except RateLimitError as e:
                last_error = e
                logger.warning(
                    f"[groq] Rate limit (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except APITimeoutError as e:
                last_error = e
                logger.error(
                    f"[groq] Timeout (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except APIError as e:
                logger.error(f"[groq] API error: {e.status_code} — {e.message}")
                raise
            except Exception as e:
                logger.error(f"[groq] Request failed: {e}")
                raise

        raise last_error

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()

        try:
            stream = await client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    yield token
        except Exception as e:
            logger.error(f"[groq] Stream failed: {e}")
            raise

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
            logger.warning(f"[groq] JSON parse failed: {raw[:200]}")
            return {}

    async def is_healthy(self) -> bool:
        try:
            client = self._get_client()
            models = await client.models.list()
            return models is not None
        except Exception as e:
            logger.warning(f"[groq] Health check failed: {e}")
            return False
