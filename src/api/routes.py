# src/api/routes.py

from fastapi import APIRouter, Request, HTTPException, status
from src.api.schemas import ResearchRequest, ResearchReport
from src.config.logger import get_logger
from src.config.settings import settings

logger = get_logger(__name__)

router = APIRouter(tags=["research"])


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "Research Agent API"}


@router.post("/research", response_model=ResearchReport)
async def research(request: ResearchRequest, req: Request) -> ResearchReport:
    """Execute a research query and return a structured report."""
    logger.info(f"Research request: {request.query}")

    agent = req.app.state.agent

    effective_max = min(
        request.max_sources,
        settings.MAX_SEARCH_RESULTS,
    )
    if effective_max != request.max_sources:
        logger.warning(
            "Clamped max_sources from %d to %d",
            request.max_sources,
            effective_max,
        )

    report = await agent.run(
        request.query,
        max_sources=effective_max,
    )

    logger.info(f"Research complete: {len(report.findings)} findings")
    return report
