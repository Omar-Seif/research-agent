# src/core/llm_client.py

import asyncio
import random
import openai
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from src.utils.exceptions import (
    ConfigurationError,
    ExternalAPITimeoutError,
    ExternalAPIRateLimitError,
    ExternalAPIResponseError,
    UnexpectedStatusError,
    InputValidationError,
    UnexpectedError,
)


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    finish_reason: str  # "stop", "tool_calls", "length"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class GroqLLMClient:
    """
    Client for interacting with LLM API.

    Wraps the OpenAI-compatible SDK to provide a clean interface for tools.
    Handles retries for transient failures and translates SDK exceptions
    to domain exceptions.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "llama-3.1-8b-instant",
        request_timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=request_timeout,
        )
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_timeout = request_timeout

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """
        Send messages to the LLM and get a response.

        Handles retries for transient failures (timeout, rate limit, network errors).
        Non-retryable failures (auth, validation) fail immediately.
        Unexpected exceptions are wrapped in UnexpectedError and fail immediately.
        """
        for attempt in range(self.max_retries):
            try:
                return await self._call_api(messages, tools)
            except (ExternalAPITimeoutError, ExternalAPIRateLimitError) as e:
                if attempt == self.max_retries - 1:
                    raise
                # Respect retry_after if provided
                if hasattr(e, "retry_after") and e.retry_after:
                    await asyncio.sleep(e.retry_after)
                else:
                    await asyncio.sleep(self._get_backoff_delay(attempt))
            except (ConfigurationError, InputValidationError):
                # Don't retry auth or validation errors
                raise
            except Exception as e:
                # Unexpected — wrap and fail immediately
                raise UnexpectedError(
                    message="Unexpected error during LLM request",
                    tool_name="llm",
                    input_snippet=str(messages)[:200],
                ) from e

    async def _call_api(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """
        Internal method that makes the actual API call and translates
        SDK exceptions to custom exceptions.
        """
        try:
            # Build kwargs conditionally — don't send None values
            kwargs = {
                "model": self.model,
                "messages": messages,
                "timeout": self.request_timeout,
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await self.client.chat.completions.create(**kwargs)

        except openai.AuthenticationError as e:
            raise ConfigurationError(
                message="Invalid Groq API key. Please check your GROQ_API_KEY environment variable.",
                tool_name="llm",
            ) from e

        except openai.APITimeoutError as e:
            raise ExternalAPITimeoutError(
                message="LLM request timed out",
                tool_name="llm",
            ) from e

        except openai.APIConnectionError as e:
            raise ExternalAPITimeoutError(
                message="Failed to connect to LLM API",
                tool_name="llm",
                input_snippet=str(e)[:100],
            ) from e

        except openai.RateLimitError as e:
            retry_after = None
            if hasattr(e, "response") and hasattr(e.response, "headers"):
                retry_after_str = e.response.headers.get("retry-after")
                if retry_after_str:
                    try:
                        retry_after = int(retry_after_str)
                    except ValueError:
                        pass
            raise ExternalAPIRateLimitError(
                message="LLM rate limit exceeded",
                tool_name="llm",
                retry_after=retry_after,
            ) from e

        except openai.BadRequestError as e:
            # Must come before APIStatusError (subclass)
            raise InputValidationError(
                message=f"Invalid request parameters (HTTP {e.status_code}): {e.message}",
                tool_name="llm",
                input_snippet=str(messages)[:200],
            ) from e

        except openai.APIStatusError as e:
            raise UnexpectedStatusError(
                message=f"LLM API returned error: {e.status_code}",
                tool_name="llm",
                http_status_code=e.status_code,
            ) from e

        except openai.APIError as e:
            raise ExternalAPIResponseError(
                message=f"LLM API error: {e}",
                tool_name="llm",
            ) from e

        # Extract the response
        choice = response.choices[0]
        message = choice.message

        tool_calls = None
        if message.tool_calls:
            tool_calls = [tc.model_dump() for tc in message.tool_calls]

        return LLMResponse(
            finish_reason=choice.finish_reason,
            content=message.content,
            tool_calls=tool_calls,
        )

    def _get_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff with small jitter."""
        delay = self.retry_delay * (2**attempt)
        jitter = random.uniform(-0.1, 0.1) * delay
        return max(0.1, delay + jitter)
