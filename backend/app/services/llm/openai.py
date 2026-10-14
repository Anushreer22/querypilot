"""OpenAI LLM client implementation using httpx with exponential backoff retries."""

import asyncio
import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm.base import (
    LLMClient,
    LLMInvalidResponse,
    LLMRateLimit,
    LLMTimeout,
    LLMUnavailable,
    ToolCall,
    ToolCompletionResult,
)

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 0.5


class OpenAILLMClient(LLMClient):
    """Direct HTTP client for OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        self.max_output_tokens = max_output_tokens or settings.llm_max_output_tokens
        self.temperature = temperature if temperature is not None else settings.llm_temperature

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Request structured JSON completion from OpenAI with transient retry logic."""
        if not self.api_key:
            raise LLMUnavailable(
                "OpenAI API key is not configured. Set OPENAI_API_KEY in environment or use LLM_PROVIDER=fake."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "response_format": {"type": "json_object"},
        }

        retries = 0
        backoff = INITIAL_BACKOFF_SECONDS

        while True:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)

                # Transient errors retry
                if response.status_code in TRANSIENT_STATUS_CODES and retries < MAX_RETRIES:
                    retries += 1
                    logger.warning(
                        "Transient error %d from OpenAI API on attempt %d. Retrying in %.2fs...",
                        response.status_code,
                        retries,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue

                if response.status_code == 429:
                    raise LLMRateLimit(
                        f"OpenAI rate limit exceeded (HTTP 429): {response.text[:200]}",
                        status_code=429,
                    )

                if response.status_code >= 500:
                    raise LLMUnavailable(
                        f"OpenAI service unavailable (HTTP {response.status_code}): {response.text[:200]}",
                        status_code=response.status_code,
                    )

                if response.status_code != 200:
                    # Permanent error - do not retry blindly
                    raise LLMUnavailable(
                        f"OpenAI API error (HTTP {response.status_code}): {response.text[:200]}",
                        status_code=response.status_code,
                    )

                response_data = response.json()
                choices = response_data.get("choices", [])
                if not choices:
                    raise LLMInvalidResponse("OpenAI returned response with no choices")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise LLMInvalidResponse("OpenAI returned empty message content")

                try:
                    parsed_json = json.loads(content)
                except json.JSONDecodeError as err:
                    raise LLMInvalidResponse(f"Failed to parse LLM response as JSON: {err}") from err

                if not isinstance(parsed_json, dict):
                    raise LLMInvalidResponse("LLM JSON output root must be an object/dict")

                return parsed_json

            except httpx.TimeoutException as err:
                raise LLMTimeout(
                    f"OpenAI request timed out after {self.timeout_seconds} seconds"
                ) from err
            except (httpx.ConnectError, httpx.NetworkError) as err:
                if retries < MAX_RETRIES:
                    retries += 1
                    logger.warning(
                        "Network connection error to OpenAI API on attempt %d. Retrying in %.2fs...",
                        retries,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise LLMUnavailable(f"Network error connecting to OpenAI: {err}") from err

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ToolCompletionResult:
        """Request completion with tools from OpenAI chat completions API."""
        if not self.api_key:
            raise LLMUnavailable(
                "OpenAI API key is not configured. Set OPENAI_API_KEY in environment or use LLM_PROVIDER=fake."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        retries = 0
        backoff = INITIAL_BACKOFF_SECONDS

        while True:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code in TRANSIENT_STATUS_CODES and retries < MAX_RETRIES:
                    retries += 1
                    logger.warning(
                        "Transient error %d from OpenAI API in complete_with_tools on attempt %d. Retrying in %.2fs...",
                        response.status_code,
                        retries,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue

                if response.status_code == 429:
                    raise LLMRateLimit(
                        f"OpenAI rate limit exceeded (HTTP 429): {response.text[:200]}",
                        status_code=429,
                    )

                if response.status_code >= 500:
                    raise LLMUnavailable(
                        f"OpenAI service unavailable (HTTP {response.status_code}): {response.text[:200]}",
                        status_code=response.status_code,
                    )

                if response.status_code != 200:
                    raise LLMUnavailable(
                        f"OpenAI API error (HTTP {response.status_code}): {response.text[:200]}",
                        status_code=response.status_code,
                    )

                response_data = response.json()
                choices = response_data.get("choices", [])
                if not choices:
                    raise LLMInvalidResponse("OpenAI returned response with no choices")

                message_dict = choices[0].get("message", {})
                raw_tool_calls = message_dict.get("tool_calls")
                content = message_dict.get("content")

                if raw_tool_calls:
                    parsed_tool_calls: list[ToolCall] = []
                    for tc in raw_tool_calls:
                        call_id = tc.get("id", "")
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        raw_args = fn.get("arguments", "{}")

                        try:
                            args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError as err:
                            raise LLMInvalidResponse(
                                f"Failed to parse tool call arguments for '{fn_name}' as JSON: {err}"
                            ) from err

                        if not isinstance(args_dict, dict):
                            raise LLMInvalidResponse(f"Tool call arguments for '{fn_name}' must be a JSON object")

                        parsed_tool_calls.append(
                            ToolCall(
                                id=call_id,
                                name=fn_name,
                                arguments=args_dict,
                            )
                        )
                    return ToolCompletionResult(tool_calls=parsed_tool_calls, content=content)

                if content is not None:
                    return ToolCompletionResult(tool_calls=None, content=content)

                raise LLMInvalidResponse("OpenAI returned response with neither tool_calls nor content")

            except httpx.TimeoutException as err:
                raise LLMTimeout(
                    f"OpenAI request timed out after {self.timeout_seconds} seconds"
                ) from err
            except (httpx.ConnectError, httpx.NetworkError) as err:
                if retries < MAX_RETRIES:
                    retries += 1
                    logger.warning(
                        "Network connection error to OpenAI API in complete_with_tools on attempt %d. Retrying in %.2fs...",
                        retries,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise LLMUnavailable(f"Network error connecting to OpenAI: {err}") from err


