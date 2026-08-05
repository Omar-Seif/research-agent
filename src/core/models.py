# src/core/models.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, HttpUrl


class SearchResult(BaseModel):
    """A single result from a web search."""

    url: HttpUrl = Field(..., description="The URL of the search result")
    title: Optional[str] = Field(None, description="The title from the search result")
    snippet: Optional[str] = Field(
        None, description="A short preview from the search engine"
    )


class ArticleContent(BaseModel):
    """The full content of a fetched article."""

    url: HttpUrl = Field(..., description="The URL this content was fetched from")
    title: str = Field(..., description="The actual page title from the HTML")
    content: str = Field(..., description="The full text content of the article")
    fetch_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this content was fetched (UTC)",
    )


class ExtractedFact(BaseModel):
    """A fact extracted from an article by the LLM."""

    id: UUID = Field(
        default_factory=uuid4, description="Unique identifier for this extracted fact"
    )
    statement: str = Field(
        ..., description="The fact statement extracted from the article"
    )
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in extraction quality (0.0-1.0)",
    )
    source_urls: List[HttpUrl] = Field(
        ..., description="URLs of articles that support this fact"
    )
    evidence: Optional[str] = Field(
        None, description="Excerpt from the article that supports the fact"
    )


# FactCheckResult was removed — see README ADR "Remove Fact-Checking Stage" for reasoning.


@dataclass
class ResearchState:
    """Mutable working state of the research pipeline."""

    query: str
    search_results: List[SearchResult] = field(default_factory=list)
    articles: List[ArticleContent] = field(default_factory=list)
    extracted_facts: List[ExtractedFact] = field(default_factory=list)
