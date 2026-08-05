# src/core/llm_client.py

import asyncio
import random
import openai
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from src.config.logger import get_logger
from src.utils.exceptions import (
    ConfigurationError,
    ExternalAPITimeoutError,
    ExternalAPIRateLimitError,
    ExternalAPIResponseError,
    UnexpectedStatusError,
    InputValidationError,
    UnexpectedError,
    ContextWindowExceededError,
    MalformedResponseError,
)

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    finish_reason: str  # "stop", "tool_calls", "length"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class GroqLLMClient:
    """Client for interacting with Groq's LLM API."""

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
        tool_choice: Optional[str] = None,  # "auto", "required", or "none"
    ) -> LLMResponse:
        """Send messages to the LLM and get a response."""
        for attempt in range(self.max_retries):
            try:
                return await self._call_api(messages, tools, tool_choice)
            except (
                ExternalAPITimeoutError,
                ExternalAPIRateLimitError,
                MalformedResponseError,
            ) as e:
                if attempt == self.max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt+1}/{self.max_retries} failed with {type(e).__name__}, no more retries"
                    )
                    raise
                logger.debug(
                    f"Attempt {attempt+1}/{self.max_retries} failed with {type(e).__name__}, retrying..."
                )
                # Respect retry_after if provided
                if hasattr(e, "retry_after") and e.retry_after:
                    await asyncio.sleep(e.retry_after)
                else:
                    await asyncio.sleep(self._get_backoff_delay(attempt))
            except (
                ConfigurationError,
                InputValidationError,
                ContextWindowExceededError,
            ):
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
        tool_choice: Optional[str] = None,
    ) -> LLMResponse:
        """Internal method that makes the actual API call and translates SDK exceptions to custom exceptions."""
        try:
            # Build kwargs conditionally — don't send None values
            kwargs = {
                "model": self.model,
                "messages": messages,
                "timeout": self.request_timeout,
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"

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
            # Parse the error body to detect specific failure modes
            error_code = None
            error_message = ""
            try:
                error_body = e.response.json() if hasattr(e, "response") else {}
                error_info = error_body.get("error", {})
                error_code = error_info.get("code")
                error_message = error_info.get("message", "")
            except Exception:
                pass

            # Case 1: Tool-use failure — model produced malformed tool arguments
            if error_code == "tool_use_failed":
                raise MalformedResponseError(
                    message=f"Model produced malformed tool arguments: {e.message}",
                    tool_name="llm",
                    input_snippet=str(messages)[:200],
                ) from e

            # Case 2: Request too large — Groq sometimes returns this as a 400
            # with a specific message instead of a 413. This is a heuristic based
            # on observed API behavior, not a documented contract.
            if "reduce the length" in error_message.lower():
                raise ContextWindowExceededError(
                    message=f"Request too long: {error_message}",
                    tool_name="llm",
                ) from e

            # Default: invalid request parameters
            raise InputValidationError(
                message=f"Invalid request parameters (HTTP {e.status_code}): {e.message}",
                tool_name="llm",
                input_snippet=str(messages)[:200],
            ) from e

        except openai.APIStatusError as e:
            # Check for specific status codes
            if e.status_code == 413:
                # Payload Too Large — the request exceeds the model's token limit
                raise ContextWindowExceededError(
                    message=f"Request exceeds token limit: {e.message}",
                    tool_name="llm",
                ) from e

            # Other 4xx/5xx errors that aren't rate limits
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
