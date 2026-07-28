# src/core/models.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, HttpUrl


class SearchResult(BaseModel):
    """
    A single result from a web search.

    Contains just enough information to decide which URLs to fetch.
    The snippet is a preview from the search engine, not the full content.
    """

    url: HttpUrl = Field(..., description="The URL of the search result")
    title: Optional[str] = Field(None, description="The title from the search result")
    snippet: Optional[str] = Field(
        None, description="A short preview from the search engine"
    )


class ArticleContent(BaseModel):
    """
    The full content of a fetched article.

    This is the "source" — the article itself. Contains the full text
    that will be passed to the LLM for fact extraction.
    """

    url: HttpUrl = Field(..., description="The URL this content was fetched from")
    title: str = Field(..., description="The actual page title from the HTML")
    content: str = Field(..., description="The full text content of the article")
    fetch_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this content was fetched (UTC)",
    )


class ExtractedFact(BaseModel):
    """
    A fact extracted from an article by the LLM.

    This is the raw extraction before verification. The extraction_confidence
    reflects the model's confidence in the extraction quality, not the truth
    of the statement itself.
    """

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


class FactCheckResult(BaseModel):
    """
    Result of verifying a fact against available evidence.

    Links back to the original ExtractedFact by ID and provides a verified
    confidence score. verification_confidence reflects how confident the
    model is that the fact is actually true.
    """

    extracted_fact_id: UUID = Field(
        ..., description="ID of the ExtractedFact this result corresponds to"
    )
    is_supported: bool = Field(
        ..., description="Whether the fact is supported by available evidence"
    )
    verification_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence that the fact is actually true (0.0-1.0)",
    )
    supporting_evidence: Optional[str] = Field(
        None, description="Evidence that supports the fact"
    )
    conflicting_evidence: Optional[str] = Field(
        None, description="Any evidence that contradicts the fact"
    )


@dataclass
class ResearchState:
    """
    Mutable working state of the research pipeline.

    This is a dataclass because it accumulates results as the pipeline progresses.
    Each component already has Pydantic validation, so we don't need validation
    at the container level.
    """

    query: str
    search_results: List[SearchResult] = field(default_factory=list)
    articles: List[ArticleContent] = field(default_factory=list)
    extracted_facts: List[ExtractedFact] = field(default_factory=list)
    fact_checks: List[FactCheckResult] = field(default_factory=list)
