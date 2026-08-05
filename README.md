# Research Agent

An AI-powered research agent that takes a natural-language query, searches the web, fetches and reads relevant articles, extracts structured facts using an LLM, and returns a structured JSON research report with findings, sources, and confidence scores.

Built as a learning project focused on AI system orchestration: tool design, dependency injection, structured LLM outputs, retry/error-handling strategy, and production-style API design — not just "get it working."

---

## Quick Start

### Prerequisites
- Python 3.12
- A [Groq API key](https://console.groq.com) (free tier)
- A [Tavily API key](https://tavily.com) (free tier)
- Docker (optional, for containerized run)

### Run locally

```bash
git clone https://github.com/Omar-Seif/research-agent.git
cd research-agent

conda create -n research-agent python=3.12
conda activate research-agent

pip install -r requirements.txt
cp .env.example .env
# edit .env and add your GROQ_API_KEY and TAVILY_API_KEY

python -m uvicorn src.api.main:app --reload
```

### Run with Docker

```bash
cp .env.example .env
# edit .env with your API keys
docker compose up --build
```

### Try it

```bash
curl http://localhost:8000/api/health

curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"query": "giant panda diet", "max_sources": 3}'
```

Interactive API docs (Swagger UI) are available at `http://localhost:8000/api/docs` once the server is running.

---

## Pipeline Overview

User Query  
      │     
      ▼     
Web Search (Tavily)     
      │     
      ▼     
Fetch Articles (httpx + trafilatura)      
      │     
      ▼     
Extract Facts (Groq LLM, forced tool-calling)   
      │     
      ▼     
Build Sources & Findings      
      │     
      ▼     
Generate Summary (Groq LLM, plain completion)   
      │     
      ▼     
Research Report   


Each stage is a standalone, independently testable `BaseTool` implementation. The `ResearchAgent` orchestrates the sequence, degrades gracefully on partial failures, and assembles the final report.

---

## Architecture Decisions

### Groq over OpenAI
LLM inference uses Groq's free tier via the OpenAI-compatible SDK (`base_url` override). This keeps the codebase provider-agnostic — switching providers is a configuration change, not a rewrite.

### Exception Hierarchy
Rather than one exception class per tool, exceptions are organized **by failure type**, with a single `ResearchAgentError` root. Context (`tool_name`, `input_snippet`, etc.) is carried as instance data, not encoded into the class hierarchy. Native exception chaining (`raise ... from e`) preserves original causes instead of a manual "underlying cause" field.

ResearchAgentError      
├── ConfigurationError    
├── ExternalAPITimeoutError         
├── ExternalAPIRateLimitError       
├── ExternalAPIResponseError        
│ ├── MalformedResponseError        
│ ├── UnexpectedStatusError         
│ └── ContextWindowExceededError          
├── InputValidationError            
├── ToolDependencyError       
├── FetchContentError         
│ ├── DeadLinkError           
│ ├── BlockedRequestError           
│ └── InvalidContentTypeError       
├── OrchestrationError        
│ ├── WorkflowInterruptedError            
│ └── ResourceExhaustedError        
└── UnexpectedError           


### Internal Models vs. API Schemas
Two distinct model layers exist to decouple pipeline internals from the public contract:

- `src/core/models.py` — internal pipeline state (`SearchResult`, `ArticleContent`, `ExtractedFact`, `ResearchState`)
- `src/api/schemas.py` — public request/response contracts (`ResearchRequest`, `Source`, `Finding`, `ResearchReport`)

ResearchRequest         
      │           
      ▼           
─────────────────      
Internal Pipeline       
─────────────────        
SearchResult → ArticleContent → ExtractedFact → ResearchState           
─────────────────        
      │           
      ▼           
ResearchReport          


Sources are assigned deterministic, hash-based IDs (first 16 hex chars of a SHA-256 hash of the canonical URL) enabling stable deduplication and cross-referencing without positional-index fragility.

### GroqLLMClient
A single class wraps all LLM communication: retries with exponential backoff + jitter, SDK-to-domain exception translation, and a uniform `LLMResponse` model returned to callers instead of raw SDK objects. Every tool that needs LLM inference depends on this abstraction, not on `openai` directly.

### Generic `BaseTool[InputT, OutputT]`
All pipeline tools share a common `execute()` contract via Python generics, giving each tool a strongly-typed input/output signature without forcing artificial input/output uniformity across genuinely different tools.

---

## Individual Tools

### Web Search (`WebSearchTool`)
- Uses Tavily's async client, returns internal `SearchResult` models (provider details never leak downstream).
- Domain allowlisting via `SEARCH_INCLUDE_DOMAINS` (config, not hardcoded).
- Tavily SDK exceptions are translated into the project's domain exception hierarchy.

### Fetch Articles (`FetchArticlesTool`)
- `httpx.AsyncClient` for fetching, `trafilatura` for main-content extraction (deliberately not hand-rolled with BeautifulSoup — the project's learning goal is orchestration, not HTML-boilerplate-stripping).
- Streams responses in chunks with a size cap, checking `Content-Length` first and aborting mid-stream if needed — avoids downloading huge or misreported-size pages.
- Per-URL failures (dead links, blocked requests, wrong content type) are logged and skipped; one bad URL never kills the batch.

### Extract Facts (`ExtractFactsTool`)
The reasoning stage: takes `List[ArticleContent]`, returns `List[ExtractedFact]` via an LLM.

- **One LLM call per article**, not batched — keeps source attribution unambiguous and prevents one large article from blocking others.
- **Forced tool-calling** (`tool_choice="required"`) instead of prompt-only JSON — eliminates the class of failures caused by markdown fences, stray prose, or malformed freeform JSON.
- **Retryable vs. non-retryable failures are distinguished explicitly**:

  | Failure | Cause | Exception | Retried? |
  |---|---|---|---|
  | Rate limit | HTTP 429 | `ExternalAPIRateLimitError` | ✅ |
  | Timeout | Network/API | `ExternalAPITimeoutError` | ✅ |
  | Malformed tool call | Invalid function arguments | `MalformedResponseError` | ✅ |
  | Context window exceeded | HTTP 413 *or* HTTP 400 with a length-related message | `ContextWindowExceededError` | ❌ |
  | Invalid request | HTTP 400 (other) | `InputValidationError` | ❌ |

- **Graceful degradation**: a failed article is logged and skipped; the pipeline continues with whatever succeeded.

**Production issue discovered:** Groq/Llama occasionally wraps valid JSON in a non-standard `<function=...>...</function>` tag instead of the expected tool-call format, causing an HTTP 400 (`tool_use_failed`). This is a *probabilistic* model behavior, not a deterministic bug — retrying the same request can succeed. Observed directly: the same article succeeded in one run and exhausted all 3 retries in the very next run, with no code changes between them. This is treated as retryable; genuinely non-retryable failures (bad input, context-window overflow) are not retried, since retrying identical oversized input can never succeed.

**Known limitation:** large articles are currently skipped, not chunked. Chunking + merging facts across chunks is a natural future extension.

### Fact-Checking Stage — Cut from Scope
A `FactCheckTool` was designed but deliberately removed before implementation. Verifying each extracted fact would require a second LLM call per fact, roughly doubling LLM load on top of an already rate-limit-constrained free tier, for a feature that added latency without teaching new orchestration concepts. **Tradeoff, stated plainly:** `Finding.confidence` in the final report reflects the LLM's *extraction* confidence ("did I pull this correctly from the text"), not independent *truth* verification. This is documented, not hidden.

---

## Agent Orchestration (`ResearchAgent`)

Coordinates the full pipeline and assembles the final `ResearchReport`.

- Reuses the same `GroqLLMClient` instance from `ExtractFactsTool` for summary generation, rather than constructing a second client.
- Summary generation uses a plain chat completion (no tool-calling) — prose output doesn't benefit from forced structured calling, and this avoids re-exposing the same tool-call reliability issue for a stage that doesn't need it.
- `overall_confidence` = mean of all findings' extraction confidence.
- **Sources are filtered to only those that actually contributed a finding** — a successfully fetched article can still yield zero facts (probabilistic LLM failure), and listing it as a "source" of a report it didn't contribute to would be misleading. The report distinguishes `sources_fetched` (successfully fetched) from `sources` (actually used).
- Early-exit paths (no search results / no articles fetched / no facts extracted) return a well-formed, minimally-valid empty report rather than propagating an exception for what is normal pipeline behavior.

**Production issues discovered during integration:**
- Groq sometimes signals "request too large" via **HTTP 400 with a message pattern** (`"reduce the length..."`) instead of the expected HTTP 413 — both are now normalized to `ContextWindowExceededError`.
- Some sites (e.g., Reuters) return **HTTP 401** rather than 403 when blocking automated fetches — both now map to `BlockedRequestError`.

---

## API Layer (FastAPI)

- **Application factory** (`create_app()`) + `lifespan` context manager: expensive dependencies (`GroqLLMClient`, all tools, the `ResearchAgent`) are constructed **once at startup**, stored on `app.state`, and reused across every request — not rebuilt per-request.
- **Layered structure**: `main.py` (composition/startup), `routes.py` (HTTP endpoints only), `exception_handlers.py` (domain exception → HTTP status mapping).
- **Domain exceptions never become HTTP exceptions inside route handlers.** Routes let exceptions propagate; registered FastAPI exception handlers do the translation. (Earlier draft had a bug where the route's own try/except silently converted every domain exception to a generic 500, bypassing the mapping entirely — fixed.)

  | Exception | HTTP Status |
  |---|---|
  | `InputValidationError` | 400 |
  | `ExternalAPIRateLimitError` | 429 |
  | `ExternalAPITimeoutError` | 504 |
  | `ContextWindowExceededError` | 413 |
  | `MalformedResponseError` | 502 |
  | `ConfigurationError` / `UnexpectedError` / unmapped | 500 |

- **`max_sources` is clamped server-side**: `effective_max = min(request.max_sources, settings.MAX_SEARCH_RESULTS)`, so a client can request fewer sources for a faster response but can never exceed the operator-configured ceiling.
- CORS origins and the API path prefix are environment-configurable, not hardcoded.

---

## Known Limitations

- **Tavily `include_domains` is not a reliable hard filter.** The parameter is passed correctly on every request (confirmed via isolated testing and request logging), but Tavily occasionally returns results outside the configured allowlist. This was reproduced directly and corroborated by reports in Tavily's own community forum. No client-side filtering is applied as a workaround, since discarding out-of-allowlist results could leave zero usable sources with no way to request replacements from an already-spent search budget.
- **Search quality depends heavily on query specificity.** Ambiguous queries (e.g., `"giant panda diet"` matching a grocery chain named GIANT) can return irrelevant sources even with domain filtering configured. Query reformulation/augmentation is out of scope for this project.
- **Large articles are skipped, not chunked**, when they exceed the model's effective context window under free-tier rate limits.
- **No independent fact-checking/verification stage** (see "Fact-Checking Stage" above) — confidence scores reflect extraction quality, not truth.
- **Automated test coverage is partial.** `WebSearchTool` has unit tests demonstrating the testing approach (`pytest`, `pytest-asyncio`, `AsyncMock` for SDK mocking, exception-translation testing). The remaining modules were validated extensively through manual, real-API integration testing during development, documented throughout this README, but do not yet have automated test coverage. This is a known gap, stated plainly rather than left implicit.
- **`llama-3.1-8b-instant` has a non-trivial failure rate on strict tool-calling.** Malformed tool-call generation is retried automatically, but retries don't always succeed — observed directly with the same article passing in one run and failing all 3 retries in the next. A larger/more capable model would likely reduce this; `max_retries` can be tuned at the cost of latency.

---

## Lessons Learned

A few things worth naming explicitly, since they were the most valuable parts of building this:

- **A committed API key, caught and fixed properly.** Early in the project, a Groq API key was briefly committed to a feature branch. It was diagnosed via `git log --all -p`, confirmed never to have reached the remote's `main` branch, removed via commit amend, and the key was rotated regardless. This is documented as a real incident and its resolution, not scrubbed from history.
- **Manual, real-API testing found bugs no mock ever would.** A `tool_choice=null` bug that broke every non-tool LLM call, Groq's inconsistent 413-vs-400 signaling for oversized requests, and Tavily's non-strict domain filtering were all discovered by hitting real APIs and reading real error bodies carefully — not by writing more unit tests.
- **The same exception-swallowing bug pattern appeared three separate times** (in `fetch_articles.py`, in `llm_client.py`'s retry loop, and in a `BadRequestError`-handling branch): a specific, correctly-raised custom exception getting silently recaptured by an overly broad `except` clause sitting between where it was raised and where it was meant to be caught. Worth remembering as a general debugging habit: when a specific exception isn't reaching where you expect, check every layer in between for a catch-all that's swallowing it first.
- **Scope cuts are a legitimate engineering decision when named explicitly.** Both the fact-checking stage and full test coverage were cut deliberately, under real constraints (free-tier rate limits, project time), and documented with the actual tradeoff stated — rather than silently dropped or left implicit.

---

## Project Structure

research-agent/         
├── src/          
│ ├── api/        
│ │ ├── main.py # App factory, lifespan, dependency composition         
│ │ ├── routes.py # HTTP endpoints        
│ │ ├── exception_handlers.py # Domain exception → HTTP status mapping        
│ │ └── schemas.py # API request/response Pydantic models         
│ │         
│ ├── core/             
│ │ ├── models.py # Internal pipeline Pydantic models + ResearchState         
│ │ ├── agent.py # ResearchAgent orchestrator         
│ │ ├── llm_client.py # GroqLLMClient           
│ │ └── tools/          
│ │  │ ├── base.py # Generic BaseTool[InputT, OutputT]         
│ │  │ ├── web_search.py # WebSearchTool (Tavily)        
│ │  │ ├── fetch_articles.py # FetchArticlesTool (httpx + trafilatura)           
│ │  │ └── extract_facts.py # ExtractFactsTool (Groq, forced tool-calling)       
│ │         
│ ├── config/           
│ │ ├── settings.py # Pydantic BaseSettings           
│ │ └── logger.py # Structured logging setup          
│ │         
│ └── utils/            
│ ├── exceptions.py # Domain exception hierarchy            
│ ├── hashing.py # Deterministic source ID generation             
│ └── text.py # Shared text utilities (truncate, etc.)            
│           
├── tests/        
│ ├── fixtures/         
│ │ └── mock_data.py # Sample API response payloads         
│ ├── conftest.py       
│ └── test_tools.py # WebSearchTool unit tests        
│           
├── logs/ # Runtime logs (gitignored, volume-mounted in Docker)         
│           
├── Dockerfile          
├── docker-compose.yml        
├── .dockerignore             
├── .env.example        
├── .gitignore          
├── pyproject.toml            
├── requirements.txt          
├── requirements-dev.txt            
└── README.md           
      

---

## Tech Stack

- **API**: FastAPI, Uvicorn
- **LLM**: Groq (Llama 3.1 8B Instant) via the OpenAI-compatible SDK
- **Search**: Tavily
- **HTTP**: httpx (async)
- **Content extraction**: trafilatura
- **Validation**: Pydantic v2 / pydantic-settings
- **Testing**: pytest, pytest-asyncio
- **Containerization**: Docker, Docker Compose