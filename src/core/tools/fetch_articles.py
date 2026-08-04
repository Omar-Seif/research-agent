# src/core/tools/fetch_articles.py

import re
import httpx
import trafilatura
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from src.core.models import ArticleContent
from src.core.tools.base import BaseTool
from src.config.logger import get_logger
from src.utils.exceptions import (
    InputValidationError,
    ExternalAPITimeoutError,
    DeadLinkError,
    BlockedRequestError,
    InvalidContentTypeError,
    ExternalAPIResponseError,
    ResearchAgentError,
    UnexpectedError,
)

logger = get_logger(__name__)


class FetchArticlesTool(BaseTool[List[str], List[ArticleContent]]):
    """
    Tool that fetches and extracts article content from a list of URLs.

    Handles HTTP fetching, Content-Type validation, and HTML-to-text extraction.
    Skips failed URLs gracefully and returns only successful articles.
    """

    def __init__(
        self,
        timeout: int = 30,
        max_content_bytes: int = 10 * 1024 * 1024,  # 10MB roughly 10,000,000
        user_agent: str = "ResearchAgent/1.0 (+https://github.com/Omar-Seif/research-agent.git)",
    ) -> None:
        super().__init__(
            name="fetch_articles",
            description="Fetch full article content from a list of URLs. Extracts clean text from HTML pages.",
        )
        self.timeout = timeout
        self.max_content_bytes = max_content_bytes
        self.user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, read=self.timeout),
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client if it was initialized."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def execute(self, input_data: List[str]) -> List[ArticleContent]:
        """
        Fetch and extract article content from a list of URLs.

        Args:
            input_data: List of URLs to fetch.

        Returns:
            List[ArticleContent]: Article content for each successfully fetched URL.

        Raises:
            InputValidationError: If input_data is None or not a list.
        """
        if not isinstance(input_data, list):
            raise InputValidationError(
                message="Input must be a list of URLs",
                tool_name=self.name,
                input_snippet=str(input_data)[:100],
            )

        if not input_data:
            return []

        articles = []
        for url in input_data:
            try:
                article = await self._fetch_single(url)
                if article:
                    articles.append(article)
            except (
                DeadLinkError,
                BlockedRequestError,
                InvalidContentTypeError,
                ExternalAPITimeoutError,
                ExternalAPIResponseError,
            ) as e:
                # Known domain failures — log as warning and continue
                logger.warning(f"Skipping {url}: {e}")
                continue
            except UnexpectedError as e:
                # Unexpected error — log at error level with traceback
                logger.error(f"Unexpected error for {url}: {e}", exc_info=True)
                continue
            except Exception as e:
                # Truly unexpected bug in our code
                logger.error(f"Unhandled error for {url}: {e}", exc_info=True)
                continue

        return articles

    async def _fetch_single(self, url: str) -> Optional[ArticleContent]:
        """
        Fetch and extract content from a single URL.

        Returns ArticleContent on success, None if content was empty.
        Raises exceptions for fatal failures (HTTP errors, timeouts, etc.).
        """
        # Validate URL
        if not url or not url.strip():
            logger.warning(f"Skipping empty URL")
            return None

        url = url.strip()

        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"Invalid URL format: {url}")
            return None

        try:
            # Stream the response to check size limit
            async with self.client.stream("GET", url) as response:
                response.raise_for_status()

                # Check Content-Type
                content_type = response.headers.get("content-type", "").lower()

                if "application/pdf" in content_type:
                    raise InvalidContentTypeError(
                        message=f"PDF content not supported",
                        tool_name=self.name,
                        input_snippet=url,
                    )
                if "image/" in content_type:
                    raise InvalidContentTypeError(
                        message=f"Image content not supported",
                        tool_name=self.name,
                        input_snippet=url,
                    )

                # Only proceed for HTML content
                if "text/html" not in content_type:
                    raise InvalidContentTypeError(
                        message=f"Unsupported content type: {content_type}",
                        tool_name=self.name,
                        input_snippet=url,
                    )

                # Check Content-Length header
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_content_bytes:
                    logger.warning(
                        f"Content too large for {url}: {content_length} bytes"
                    )
                    return None

                # Stream the body with size limit
                content_bytes = bytearray()
                async for chunk in response.aiter_bytes():
                    content_bytes.extend(chunk)
                    if len(content_bytes) > self.max_content_bytes:
                        logger.warning(f"Content exceeded limit for {url}")
                        return None

            # Decode HTML
            try:
                html = content_bytes.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                html = content_bytes.decode("latin-1", errors="ignore")

            # Extract main content using trafilatura
            extracted_text = trafilatura.extract(
                html,
                include_tables=True,
                include_comments=False,
                include_formatting=False,
            )

            # Check if extraction yielded content
            if not extracted_text or len(extracted_text.strip()) < 100:
                logger.warning(f"Extraction yielded minimal content for {url}")
                return None

            # Extract metadata
            metadata = trafilatura.extract_metadata(html)
            title = metadata.title if metadata else None

            if not title:
                # Fallback: extract title from HTML
                title_match = re.search(
                    r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL
                )
                title = title_match.group(1).strip() if title_match else "Untitled"

            return ArticleContent(
                url=url,
                title=title or "Untitled",
                content=extracted_text,
                fetch_timestamp=datetime.now(timezone.utc),
            )

        # Pass-through for already-correctly-typed exceptions
        except (
            InvalidContentTypeError,
            DeadLinkError,
            BlockedRequestError,
            ExternalAPITimeoutError,
            ExternalAPIResponseError,
        ):
            raise

        except httpx.ConnectError as e:
            raise DeadLinkError(
                message=f"Failed to connect to {url}",
                tool_name=self.name,
                input_snippet=url,
            ) from e

        except httpx.ConnectTimeout as e:
            raise ExternalAPITimeoutError(
                message=f"Connection timed out for {url}",
                tool_name=self.name,
                input_snippet=url,
            ) from e

        except httpx.ReadTimeout as e:
            raise ExternalAPITimeoutError(
                message=f"Read timed out for {url}",
                tool_name=self.name,
                input_snippet=url,
            ) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403]:
                raise BlockedRequestError(
                    message=f"Access forbidden for {url}",
                    tool_name=self.name,
                    input_snippet=url,
                ) from e
            if e.response.status_code in [404, 410]:
                raise DeadLinkError(
                    message=f"URL not found: {url}",
                    tool_name=self.name,
                    input_snippet=url,
                ) from e
            raise ExternalAPIResponseError(
                message=f"HTTP {e.response.status_code} for {url}",
                tool_name=self.name,
                input_snippet=url,
            ) from e

        except Exception as e:
            raise UnexpectedError(
                message=f"Unexpected error fetching {url}: {str(e)}",
                tool_name=self.name,
                input_snippet=url,
            ) from e
