# src/api/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config.settings import settings
from src.core.llm_client import GroqLLMClient
from src.core.tools.web_search import WebSearchTool
from src.core.tools.fetch_articles import FetchArticlesTool
from src.core.tools.extract_facts import ExtractFactsTool
from src.core.agent import ResearchAgent
from src.api.routes import router
from src.api.exception_handlers import add_exception_handlers
from src.config.logger import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup and teardown."""
    logger.info("Starting Research Agent API...")

    # Build dependencies once at startup
    llm_client = GroqLLMClient(
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
        model=settings.MODEL,
        request_timeout=settings.REQUEST_TIMEOUT,
        max_retries=settings.MAX_RETRIES,
        retry_delay=settings.RETRY_DELAY,
    )

    web_search = WebSearchTool(
        api_key=settings.TAVILY_API_KEY,
        max_results=settings.MAX_SEARCH_RESULTS,
        include_domains=settings.SEARCH_INCLUDE_DOMAINS,
    )
    logger.info(
        f"WebSearchTool configured with include_domains: {web_search.include_domains}"
    )

    fetch_articles = FetchArticlesTool(
        timeout=settings.FETCH_TIMEOUT,
        max_content_bytes=settings.MAX_CONTENT_BYTES,
        user_agent=settings.USER_AGENT,
    )

    extract_facts = ExtractFactsTool(llm_client)
    agent = ResearchAgent(web_search, fetch_articles, extract_facts)

    app.state.agent = agent
    app.state.fetch_articles = fetch_articles

    logger.info("Research Agent API ready")

    yield

    # Shutdown
    logger.info("Shutting down Research Agent API...")
    await fetch_articles.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""

    setup_logging()

    app = FastAPI(
        title="Research Agent API",
        description="AI-powered research agent that searches, fetches, and extracts facts",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=f"{settings.API_PREFIX}/docs",
        redoc_url=f"{settings.API_PREFIX}/redoc",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    add_exception_handlers(app)

    # Register routes
    app.include_router(router, prefix=settings.API_PREFIX)

    return app


# Create the app instance
app = create_app()


# For running directly with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
    )
