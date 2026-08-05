from typing import Optional

from src.utils.text import truncate


class ResearchAgentError(Exception):
    """Base class for all custom exceptions in the research agent system."""

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        input_snippet: Optional[str] = None,
        request_id: Optional[str] = None,
        user_query: Optional[str] = None,
    ) -> None:
        self.message = message
        self.tool_name = tool_name
        self.input_snippet = input_snippet
        self.request_id = request_id
        self.user_query = user_query
        super().__init__(message)

    def __str__(self) -> str:
        """Return a detailed string representation for logging."""
        parts = [self.message]
        if self.tool_name:
            parts.append(f"tool={self.tool_name}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        if self.user_query:
            parts.append(f"query={truncate(self.user_query)}")
        if self.input_snippet:
            parts.append(f"input={truncate(self.input_snippet)}")
        return " | ".join(parts)


class ConfigurationError(ResearchAgentError):
    """
    Raised when the application is misconfigured.

    Examples: missing GROQ_API_KEY, invalid LOG_LEVEL, required file not found.
    Occurs during startup and should cause the application to exit immediately.
    """

    pass


class ExternalAPITimeoutError(ResearchAgentError):
    """
    Raised when any external API call times out.

    Applies to: Groq API, search API, or any HTTP request that exceeds
    the configured timeout. The tool_name field identifies which API.
    """

    pass


class ExternalAPIRateLimitError(ResearchAgentError):
    """
    Raised when an external API rate limit is exceeded.

    Applies to: Groq API, search API, or any external API that returns
    a rate limit response (HTTP 429 or similar).
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        input_snippet: Optional[str] = None,
        request_id: Optional[str] = None,
        user_query: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(
            message=message,
            tool_name=tool_name,
            input_snippet=input_snippet,
            request_id=request_id,
            user_query=user_query,
        )

    def __str__(self) -> str:
        """Include retry_after in the string representation if available."""
        base = super().__str__()
        if self.retry_after is not None:
            return f"{base} | retry_after={self.retry_after}s"
        return base


class ExternalAPIResponseError(ResearchAgentError):
    """
    Base class for errors where an external API responded but the response was invalid.

    Subclasses cover specific response issues: malformed JSON, unexpected status codes,
    and context window limits.
    """

    pass


class MalformedResponseError(ExternalAPIResponseError):
    """
    Raised when an external API response cannot be parsed.

    Examples: JSON decode failure, missing expected fields, invalid data types.
    """

    pass


class UnexpectedStatusError(ExternalAPIResponseError):
    """
    Raised when an external API returns an unexpected HTTP status code.

    Includes 4xx and 5xx responses that aren't specifically rate limits.
    The status code and response body should be captured in the error message.
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        input_snippet: Optional[str] = None,
        request_id: Optional[str] = None,
        user_query: Optional[str] = None,
        http_status_code: Optional[int] = None,
    ) -> None:
        self.http_status_code = http_status_code
        super().__init__(
            message=message,
            tool_name=tool_name,
            input_snippet=input_snippet,
            request_id=request_id,
            user_query=user_query,
        )

    def __str__(self) -> str:
        """Include HTTP status code in the string representation if available."""
        base = super().__str__()
        if self.http_status_code is not None:
            return f"{base} | status={self.http_status_code}"
        return base


class ContextWindowExceededError(ExternalAPIResponseError):
    """
    Raised when the input exceeds the model's token limit.

    The remedy is different from other API errors — truncate the input or
    use a different model rather than retrying the same request.
    """

    pass


class InputValidationError(ResearchAgentError):
    """
    Raised when a tool receives invalid input from the orchestration layer.

    Examples: empty query, malformed URL, content too short for extraction.
    Carries the specific field that was invalid in the message.
    """

    pass


class ToolDependencyError(ResearchAgentError):
    """
    Raised when one tool depends on the output of another, but that output is missing or invalid.

    This is a bug in orchestration logic, not normal data flow.
    Example: fetch_articles called with an empty list of URLs because web_search returned nothing.
    """

    pass


class FetchContentError(ResearchAgentError):
    """
    Base class for errors that occur when fetching arbitrary web content.

    These are distinct from API errors because they involve accessing random web servers
    with unpredictable response types and failure modes.
    """

    pass


class DeadLinkError(FetchContentError):
    """
    Raised when a URL is unreachable.

    Examples: 404 Not Found, DNS resolution failure, connection refused.
    This is a permanent condition — retrying won't help.
    """

    pass


class BlockedRequestError(FetchContentError):
    """
    Raised when a site blocks the request.

    Examples: HTTP 403 Forbidden, Cloudflare challenge, bot detection.
    May be resolvable with different headers or proxies, but retrying the same request won't help.
    """

    pass


class InvalidContentTypeError(FetchContentError):
    """
    Raised when the URL returns content that can't be processed.

    Examples: PDF, image, video, binary data — anything that's not HTML or plain text.
    The response exists and is accessible, but unusable for fact extraction.
    """

    pass


class OrchestrationError(ResearchAgentError):
    """
    Base class for pipeline-level failures that aren't specific to any single tool.

    Raised when the workflow itself fails, rather than a tool within it.
    """

    pass


class WorkflowInterruptedError(OrchestrationError):
    """
    Raised when the workflow is interrupted before completion.

    Examples: user cancellation, overall timeout exceeded, external signal.
    """

    pass


class ResourceExhaustedError(OrchestrationError):
    """
    Raised when the system hits a resource limit.

    Examples: memory exceeded, disk full, execution time limit reached.
    """

    pass


class UnexpectedError(ResearchAgentError):
    """
    Catch-all for errors that weren't anticipated.

    Used in the orchestration layer to wrap any exception that doesn't match
    the known exception types. Should be rare — if it's happening frequently,
    that's a signal to add a new exception class.

    The constructor is identical to the base class — it exists to give a
    distinct type for the orchestrator's final except block.
    """

    pass
