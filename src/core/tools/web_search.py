# src/core/tools/web_search.py

from typing import List, Optional
from tavily import AsyncTavilyClient
from tavily.errors import (
    ForbiddenError as TavilyForbiddenError,
    TimeoutError as TavilyTimeoutError,
    TavilyKeylessLimitError,
)
from tavily import (
    MissingAPIKeyError,
    InvalidAPIKeyError,
    UsageLimitExceededError,
    BadRequestError,
)
from src.core.models import SearchResult
from src.core.tools.base import BaseTool
from src.utils.exceptions import (
    InputValidationError,
    ConfigurationError,
    ExternalAPITimeoutError,
    ExternalAPIRateLimitError,
    ExternalAPIResponseError,
    UnexpectedError,
)


class WebSearchTool(BaseTool[str, List[SearchResult]]):
    """
    Tool that searches the web using Tavily's API.

    Uses Tavily's async client for non-blocking search requests.
    Returns structured search results with URL, title, and snippet.
    Supports domain filtering via include_domains.
    """

    def __init__(
        self,
        api_key: str,
        max_results: int = 3,
        include_domains: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize the web search tool.

        Args:
            api_key: Tavily API key (from settings).
            max_results: Maximum number of search results to return.
            include_domains: Optional list of domains to restrict search results to.
                             If empty, no domain filtering is applied.
        """
        super().__init__(
            name="web_search",
            description="Search the web for information relevant to the user query. Returns URLs, titles, and content snippets.",
        )

        self.client = AsyncTavilyClient(api_key=api_key)
        self.max_results = max_results
        self.include_domains = include_domains or []

    async def execute(self, query: str) -> List[SearchResult]:
        """
        Execute a web search for the given query.

        Args:
            query: The search query string.

        Returns:
            List[SearchResult]: A list of search results, or an empty list if none found.

        Raises:
            InputValidationError: If query is empty or whitespace-only.
            ConfigurationError: If API key is missing or invalid.
            ExternalAPITimeoutError: If the request times out.
            ExternalAPIRateLimitError: If rate limit is exceeded.
            ExternalAPIResponseError: For other API errors.
        """
        # Validate input
        if not query or not query.strip():
            raise InputValidationError(
                message="Search query cannot be empty",
                tool_name=self.name,
                input_snippet=query,
            )

        # Prepare search parameters
        query = query.strip()
        search_kwargs = {
            "query": query,
            "max_results": self.max_results,
        }
        if self.include_domains:
            search_kwargs["include_domains"] = self.include_domains

        try:
            # Execute the search
            response = await self.client.search(**search_kwargs)

            # Extract and map results
            results = response.get("results", [])
            if not results:
                return []

            return [
                SearchResult(
                    url=item["url"],
                    title=item.get("title"),
                    snippet=item.get("content"),
                )
                for item in results
                if item.get("url")
            ]

        except MissingAPIKeyError as e:
            raise ConfigurationError(
                message="Tavily API key is missing. Please set TAVILY_API_KEY in your .env file.",
                tool_name=self.name,
                input_snippet=query,
            ) from e

        except InvalidAPIKeyError as e:
            raise ConfigurationError(
                message="Invalid Tavily API key. Please check your TAVILY_API_KEY in .env.",
                tool_name=self.name,
                input_snippet=query,
            ) from e

        except BadRequestError as e:
            raise InputValidationError(
                message=f"Invalid search request: {e}",
                tool_name=self.name,
                input_snippet=query,
            ) from e

        except TavilyForbiddenError as e:
            raise ExternalAPIResponseError(
                message=f"Tavily API access forbidden: {e}",
                tool_name=self.name,
                input_snippet=query,
            ) from e

        except TavilyTimeoutError as e:
            raise ExternalAPITimeoutError(
                message="Tavily API request timed out",
                tool_name=self.name,
                input_snippet=query,
            ) from e

        except (UsageLimitExceededError, TavilyKeylessLimitError) as e:
            retry_after = None
            if hasattr(e, "response") and hasattr(e.response, "headers"):
                retry_after_str = e.response.headers.get("retry-after")
                if retry_after_str:
                    try:
                        retry_after = int(retry_after_str)
                    except ValueError:
                        pass
            raise ExternalAPIRateLimitError(
                message=f"Tavily API rate limit exceeded: {e}",
                tool_name=self.name,
                input_snippet=query,
                retry_after=retry_after,
            ) from e

        except Exception as e:
            raise UnexpectedError(
                message="Unexpected error during web search",
                tool_name=self.name,
                input_snippet=query,
            ) from e
