# src/api/routes.py

from fastapi import APIRouter, Request, HTTPException, status
from src.api.schemas import ResearchRequest, ResearchReport
from src.config.logger import get_logger

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
    report = await agent.run(request.query, max_sources=request.max_sources)
    logger.info(f"Research complete: {len(report.findings)} findings")
    return report
