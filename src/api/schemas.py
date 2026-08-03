# src/api/schemas.py

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, field_validator


class ResearchRequest(BaseModel):
    """
    Request payload for the research endpoint.

    The model is always controlled by settings — this is just the user query
    and optional parameters for controlling the research process.
    """

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The research question or topic to investigate",
    )
    max_sources: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of sources to fetch and analyze",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """
        Ensure query has meaningful content beyond just minimum length.

        min_length=3 catches trivially short queries, but doesn't catch
        whitespace-only input. This validator handles that edge case.
        """
        if not v.strip():
            raise ValueError("Query must contain non-whitespace characters")
        return v.strip()


class Source(BaseModel):
    """
    A source referenced in the research report.

    This is the API-facing representation of an ArticleContent.
    The ID is a stable hash of the URL for deterministic deduplication.
    """

    id: str = Field(..., description="Stable identifier generated from the URL (hash)")
    url: HttpUrl = Field(..., description="The URL of the source")
    title: str = Field(..., description="The title of the source")
    snippet: Optional[str] = Field(
        None,
        description="A short preview excerpted from the article content",
        max_length=300,
    )


class Finding(BaseModel):
    """
    A verified finding from the research process.

    References sources by their stable IDs rather than by URL or position,
    making the reference robust to source reordering or deduplication.
    """

    statement: str = Field(
        ..., description="The factual statement discovered through research"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model's confidence in the accuracy of this extracted fact.",
    )
    source_ids: List[str] = Field(
        ..., description="IDs of sources that support this finding", min_length=1
    )
    evidence: Optional[str] = Field(
        None, description="Excerpt from the source that supports the finding"
    )


class ResearchReport(BaseModel):
    """
    The complete research report returned to the API client.

    Contains the original query, a human-readable summary, a list of findings,
    deduplicated sources, and metadata about the research process.
    """

    query: str = Field(..., description="The original research question")
    summary: str = Field(
        ..., description="A human-readable summary of the findings", min_length=1
    )
    findings: List[Finding] = Field(
        ..., description="The verified findings from the research"
    )
    sources: List[Source] = Field(
        ..., description="All sources referenced by the findings (deduplicated)"
    )
    overall_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall confidence in the report (0.0-1.0)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the report was generated (UTC)",
    )
    research_time_seconds: Optional[float] = Field(
        None, ge=0.0, description="How long the research took in seconds"
    )

    @field_validator("summary")
    @classmethod
    def validate_summary_not_empty(cls, v: str) -> str:
        """Ensure summary has meaningful content."""
        if not v.strip():
            raise ValueError("Summary must contain non-whitespace characters")
        return v.strip()
