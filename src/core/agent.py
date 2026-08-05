# src/core/agent.py

import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
from src.core.models import ArticleContent, ExtractedFact
from src.core.tools.web_search import WebSearchTool
from src.core.tools.fetch_articles import FetchArticlesTool
from src.core.tools.extract_facts import ExtractFactsTool
from src.api.schemas import ResearchReport, Source, Finding
from src.utils.hashing import generate_source_id
from src.utils.text import truncate
from src.utils.exceptions import ResearchAgentError, UnexpectedError
from src.config.logger import get_logger

logger = get_logger(__name__)


class ResearchAgent:
    """
    Orchestrates the research pipeline: search → fetch → extract → report.
    """

    def __init__(
        self,
        web_search_tool: WebSearchTool,
        fetch_articles_tool: FetchArticlesTool,
        extract_facts_tool: ExtractFactsTool,
    ):
        self.web_search = web_search_tool
        self.fetch_articles = fetch_articles_tool
        self.extract_facts = extract_facts_tool
        # Reuse the same LLM client from extract_facts for summary generation
        self.llm_client = self.extract_facts.llm_client

    async def run(
        self,
        query: str,
        max_sources: Optional[int] = None,
    ) -> ResearchReport:
        """Execute the full research pipeline."""
        start_time = time.perf_counter()

        try:
            # Step 1: Web search
            logger.info(f"Searching for: {query}")
            search_results = await self.web_search.execute(
                query,
                max_results=max_sources,
            )
            if not search_results:
                logger.warning("No search results found")
                return self._empty_report(
                    query,
                    "No search results found",
                    elapsed_seconds=time.perf_counter() - start_time,
                )

            # Step 2: Fetch articles
            urls = [str(r.url) for r in search_results]
            logger.info(f"Fetching {len(urls)} articles")
            articles = await self.fetch_articles.execute(urls)
            if not articles:
                logger.warning("No articles could be fetched")
                return self._empty_report(
                    query,
                    "No articles could be fetched",
                    elapsed_seconds=time.perf_counter() - start_time,
                )

            # Step 3: Extract facts
            logger.info(f"Extracting facts from {len(articles)} articles")
            facts = await self.extract_facts.execute(articles)
            if not facts:
                logger.warning("No facts could be extracted")
                return self._empty_report(
                    query,
                    "No facts could be extracted",
                    elapsed_seconds=time.perf_counter() - start_time,
                    sources_fetched=len(articles),
                )

            # Step 4: Build sources and findings
            logger.info(
                f"Building report with {len(facts)} facts from {len(articles)} sources"
            )
            all_sources = self._build_sources(articles)
            findings = self._build_findings(facts, all_sources)

            # Filter to only sources that contributed findings
            used_source_ids = {
                source_id for finding in findings for source_id in finding.source_ids
            }
            sources = [s for s in all_sources if s.id in used_source_ids]

            overall_confidence = self._compute_overall_confidence(findings)

            # Step 5: Generate summary
            logger.info("Generating summary...")
            summary = await self._generate_summary(query, findings)

            # Step 6: Assemble report
            return ResearchReport(
                query=query,
                summary=summary,
                findings=findings,
                sources=sources,
                sources_fetched=len(all_sources),
                overall_confidence=overall_confidence,
                timestamp=datetime.now(timezone.utc),
                research_time_seconds=time.perf_counter() - start_time,
            )

        except ResearchAgentError:
            # Already a domain exception — let it propagate
            raise
        except Exception as e:
            raise UnexpectedError(
                message=f"Unexpected error during research: {str(e)}",
                tool_name="agent",
                input_snippet=query,
            ) from e

    async def _generate_summary(self, query: str, findings: List[Finding]) -> str:
        """
        Generate a coherent summary paragraph from the findings.

        Uses plain LLM completion (no tool-calling) to produce prose.
        Limits to top 20 facts to avoid token issues.
        """
        if not findings:
            return f"No findings found for query: '{query}'."

        # Cap facts to avoid token limits
        FACT_LIMIT = 20
        facts_to_summarize = findings[:FACT_LIMIT]

        facts_text = "\n".join(
            [
                f"- {f.statement} (confidence: {f.confidence:.2f})"
                for f in facts_to_summarize
            ]
        )

        system_prompt = """
        You are a research summarizer. Write a concise, coherent summary paragraph synthesizing the facts provided.

        The summary should:
        - Synthesize the key information from the facts
        - Be 2-3 paragraphs (150-250 words)
        - Be written in a clear, professional tone
        - Not simply list the facts — synthesize them
        """

        user_prompt = f"""
        Research question: {query}

        Facts found:
        {facts_text}

        Write a summary paragraph answering the research question based on the facts above.
        """

        try:
            response = await self.llm_client.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                # No tools — plain content response
            )
            if response.content:
                return response.content
            return f"Found {len(findings)} findings related to: '{query}'. (Summary generation failed.)"
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Research found {len(findings)} findings related to: '{query}'. (Summary generation failed.)"

    def _build_sources(self, articles: List[ArticleContent]) -> List[Source]:
        """Build deduplicated Source objects from articles."""
        source_map: Dict[str, Source] = {}
        for article in articles:
            source_id = generate_source_id(article.url)
            if source_id not in source_map:
                source_map[source_id] = Source(
                    id=source_id,
                    url=article.url,
                    title=article.title,
                    snippet=truncate(article.content, max_length=300),
                )
        return list(source_map.values())

    def _build_findings(
        self, facts: List[ExtractedFact], sources: List[Source]
    ) -> List[Finding]:
        """Build Finding objects from ExtractedFact, mapping source URLs to IDs."""
        url_to_id = {str(s.url): s.id for s in sources}

        findings = []
        for fact in facts:
            source_ids = [
                url_to_id[str(url)] for url in fact.source_urls if str(url) in url_to_id
            ]
            if source_ids:
                findings.append(
                    Finding(
                        statement=fact.statement,
                        confidence=fact.extraction_confidence,
                        source_ids=source_ids,
                        evidence=fact.evidence,
                    )
                )
            else:
                logger.warning(
                    f"Dropping fact with no matching source: {fact.statement[:80]}... "
                    f"(source_urls: {[str(u) for u in fact.source_urls]})"
                )
        return findings

    def _compute_overall_confidence(self, findings: List[Finding]) -> float:
        """Compute overall confidence as the mean of all finding confidences."""
        if not findings:
            return 0.0
        return sum(f.confidence for f in findings) / len(findings)

    def _empty_report(
        self,
        query: str,
        reason: str,
        elapsed_seconds: float = 0.0,
        sources_fetched: int = 0,  # ← Add this parameter
    ) -> ResearchReport:
        """Return an empty report when no results are found."""
        return ResearchReport(
            query=query,
            summary=f"No results found for query: '{query}'. Reason: {reason}",
            findings=[],
            sources=[],
            sources_fetched=sources_fetched,  # ← Pass through
            overall_confidence=0.0,
            timestamp=datetime.now(timezone.utc),
            research_time_seconds=elapsed_seconds,
        )
