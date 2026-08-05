import pytest
from unittest.mock import AsyncMock

from tavily import InvalidAPIKeyError, BadRequestError
from tavily.errors import TimeoutError as TavilyTimeoutError

from src.core.models import SearchResult
from src.core.tools.web_search import WebSearchTool
from src.utils.exceptions import (
    ConfigurationError,
    InputValidationError,
    ExternalAPITimeoutError,
)

from tests.fixtures.mock_data import MOCK_TAVILY_RESPONSE

# ----------------------------
# Validation tests
# ----------------------------


@pytest.mark.parametrize("bad_query", ["", "   ", "\t\n"])
async def test_web_search_empty_query_raises_validation_error(bad_query):
    """Reject empty or whitespace-only queries before any API call."""
    tool = WebSearchTool(api_key="fake-key")

    with pytest.raises(InputValidationError):
        await tool.execute(bad_query)


# ----------------------------
# Success tests
# ----------------------------


async def test_web_search_success_returns_search_results():
    """Successful Tavily response should become SearchResult objects."""
    tool = WebSearchTool(api_key="fake-key")

    tool.client.search = AsyncMock(return_value=MOCK_TAVILY_RESPONSE)

    results = await tool.execute("python")

    tool.client.search.assert_awaited_once_with(
        query="python",
        max_results=tool.max_results,
    )

    assert len(results) == 2
    assert all(isinstance(result, SearchResult) for result in results)

    assert str(results[0].url) == "https://example.com/python"
    assert results[0].title == "Python Guide"
    assert results[0].snippet == "Python is a programming language."


async def test_web_search_success_passes_include_domains():
    """Configured include_domains should be forwarded to Tavily."""
    tool = WebSearchTool(
        api_key="fake-key",
        include_domains=["example.com"],
    )

    tool.client.search = AsyncMock(return_value=MOCK_TAVILY_RESPONSE)

    await tool.execute("python")

    tool.client.search.assert_awaited_once_with(
        query="python",
        max_results=tool.max_results,
        include_domains=["example.com"],
    )


# ----------------------------
# Exception translation tests
# ----------------------------


@pytest.mark.parametrize(
    "tavily_exception, expected_exception",
    [
        (
            InvalidAPIKeyError("Invalid API key"),
            ConfigurationError,
        ),
        (
            BadRequestError("Bad request"),
            InputValidationError,
        ),
        (
            TavilyTimeoutError("Request timed out"),
            ExternalAPITimeoutError,
        ),
    ],
    ids=[
        "invalid-api-key",
        "bad-request",
        "timeout",
    ],
)
async def test_web_search_exception_translation(
    tavily_exception,
    expected_exception,
):
    """Tavily exceptions should be translated into custom exceptions."""

    tool = WebSearchTool(api_key="fake-key")
    tool.client.search = AsyncMock(side_effect=tavily_exception)

    with pytest.raises(expected_exception):
        await tool.execute("python")
