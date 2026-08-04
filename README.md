# Research Agent

> An AI-powered research agent that takes user queries, invokes multiple tools in sequence, and returns structured, reliable findings.

---

# 🎯 Current Status

**Phase:** Project Setup & Infrastructure

The project is currently in its setup phase. The initial foundation has been completed, including:

- ✅ Project structure defined
- ✅ Development environment configured
- ✅ API client integration established
- ✅ Logging system configured

---

# 🛠️ Setup Instructions

## Prerequisites

Before getting started, ensure you have:

- Python **3.12**
- Miniconda or Anaconda
- A **Groq API Key** (free tier available)

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Omar-Seif/research-agent.git
cd research-agent
```

### 2. Create and Activate a Conda Environment

```bash
conda create -n research-agent python=3.12
conda activate research-agent
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Open the `.env` file and add your API key:

```env
GROQ_API_KEY=your-groq-api-key
```

---

# 📁 Project Structure

```text
research-agent/
├── docker/
│   └── dockerfile              # Container definition (future use)
│
├── src/
│   ├── api/                    # REST API layer
│   │   ├── routes/             # API endpoints
│   │   └── schemas/            # Pydantic models
│   │
│   ├── core/                   # Core business logic
│   │   └── tools/              # Tool implementations
│   │
│   ├── config/                 # Configuration management
│   └── utils/                  # Shared utilities
│
├── tests/
│   └── fixtures/               # Test data
│
├── logs/
│   └── .gitkeep                # Preserve logs directory
│
├── .env.example                # Environment template
├── docker-compose.yml          # Multi-container setup (future use)
├── pyproject.toml              # Project metadata
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

# 🏗️ Architecture Decisions

## Decision: Groq over OpenAI

### Context

The project requires LLM inference while keeping development costs low.

### Decision

Use the **Groq API** through the **OpenAI-compatible Python SDK**.

### Reasoning

- Groq's free tier provides sufficient quota for development.
- The OpenAI SDK supports custom `base_url`, allowing easy provider switching.
- Migrating to OpenAI (or another compatible provider) later only requires a configuration change.

### Current Implementation

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key="your-groq-api-key"
)
```

---

## Decision: Exception Hierarchy

#### Context

The research agent executes a multi-stage pipeline consisting of tools such as web search, article fetching, fact extraction, and fact checking. Although each tool performs different work, they often fail in the same ways (timeouts, rate limits, invalid responses, etc.).

Instead of creating separate exception classes for every tool, the project organizes exceptions by **failure type**.

#### Decision

The exception hierarchy is built around a shared base class:

- `ResearchAgentError` serves as the root of all custom exceptions.
- Tool-specific information (such as `tool_name`) is stored as data on the exception instance instead of being encoded in the class hierarchy.
- Native Python exception chaining (`raise ... from e`) is used to preserve the original cause of failures.

#### Exceptions Hierarchy

```text
ResearchAgentError
├── ConfigurationError
├── ExternalAPITimeoutError
├── ExternalAPIRateLimitError
├── ExternalAPIResponseError
│   ├── MalformedResponseError
│   ├── UnexpectedStatusError
│   └── ContextWindowExceededError
├── InputValidationError
├── ToolDependencyError
├── FetchContentError
│   ├── DeadLinkError
│   ├── BlockedRequestError
│   └── InvalidContentTypeError
├── OrchestrationError
│   ├── WorkflowInterruptedError
│   └── ResourceExhaustedError
└── UnexpectedError
```


---


## Decision: Separate Internal Pipeline Models from API Models

#### Context

The research agent processes data through several stages—search, content fetching, fact extraction, and fact verification. Each stage requires data structures tailored to its own responsibilities, while the API should expose a stable, consumer-friendly response format.

Using the same models for both internal processing and external responses would tightly couple the pipeline implementation to the public API, making future changes more difficult.

#### Decision

The project uses two distinct model layers:

- **Internal models** (`src/core/models.py`) represent the working state of the research pipeline.
- **API models** (`src/api/schemas.py`) define the public request and response contracts exposed by the REST API.
- Sources are assigned deterministic, hash-based identifiers using the first 16 hexadecimal characters of a SHA-256 hash of the canonical URL. These IDs are used for source deduplication and cross-referencing findings without exposing implementation details.

#### Architecture

```text
Client Request
      │
      ▼
ResearchRequest
      │
      ▼
──────────────────────────────────────
 Internal Pipeline
──────────────────────────────────────
SearchResult
      │
      ▼
ArticleContent
      │
      ▼
ExtractedFact
      │
      ▼
FactCheckResult
      │
      ▼
ResearchState
──────────────────────────────────────
      │
      ▼
ResearchReport
      │
      ▼
Client Response
```

### Context

**Separation of concerns**

Internal models are optimized for processing and orchestration, while API models are optimized for stability and usability. Changes to the internal pipeline do not require changes to the public API.

**Stable API contract**

Clients interact only with API schemas, allowing the implementation of the research pipeline to evolve without introducing breaking API changes.

**Explicit data transformations**

Each pipeline stage produces a well-defined model, making data flow easier to understand, validate, and test.

---

## Decision: Introduce a `GroqLLMClient` that encapsulates all communication with the LLM behind a single interface.

**Why**

Multiple pipeline components require LLM inference (fact extraction, verification, summarization). Rather than allowing each tool to depend directly on the OpenAI SDK, all requests pass through a single client responsible for provider communication.

**Responsibilities**

- Expose a single async `complete()` interface.
- Manage communication with the OpenAI-compatible API.
- Handle retries and exponential backoff for transient failures.
- Translate SDK exceptions into project-specific exceptions.
- Return an internal `LLMResponse` model instead of SDK objects.
- Support optional function/tool calling.

**Workflow**

```text
Pipeline Tool
      │
      ▼
GroqLLMClient
      │
      ▼
AsyncOpenAI SDK
      │
      ▼
Groq API
      │
      ▼
LLMResponse
      │
      ▼
Pipeline Tool
```

**Benefits**

- Decouples business logic from the SDK.
- Centralizes retry and error handling.
- Makes provider changes low-cost through configuration.
- Keeps the rest of the application working with domain models rather than SDK types.


---

## Decision: Generic Base Tool Abstraction

**Context:** Every research tool follows the same lifecycle (validate input → execute → return output) but operates on different data types.

**Decision:** Introduced a generic `BaseTool[InputT, OutputT]` abstract class that defines a common `execute()` contract while allowing each tool to specify its own strongly typed input and output models.

**Rationale:**
- Enforces a consistent interface across all pipeline tools.
- Uses Python generics for type safety instead of relying on `Any`.
- Makes tools interchangeable within the orchestration pipeline while preserving clear input/output contracts.
- Centralizes shared behavior without constraining tool-specific implementations.

---

## Decision: External Search Provider Configuration

**Context:** The research agent requires a web search capability to retrieve relevant sources before article fetching and fact extraction.

**Decision:** Integrate Tavily as the search provider and manage all search behavior through configuration. Search-specific settings (API key, maximum search results, and included domains) are defined in the application's configuration layer rather than hardcoded in the search tool.

**Rationale:**
- Separates application logic from deployment-specific configuration.
- Makes the search provider easy to configure without code changes.
- Uses Tavily's native domain filtering instead of implementing custom filtering logic.
- Restricts searches to a curated set of high-quality domains to improve source reliability.

---

# Individual Tools

## Web Search Tool  

### Pipeline Position

```text
Web Search        ← This tool
      │
      ▼
Fetch Articles
      │
      ▼
Extract Facts   
      │
      ▼
Fact Check
      │
      ▼
Generate Report
```

Implemented the first concrete pipeline tool: `WebSearchTool`.

**Design decisions:**
- Uses Tavily's asynchronous client for web search.
- Inherits from the generic `BaseTool[str, List[SearchResult]]`, giving the tool a strongly typed input/output contract.
- Returns internal `SearchResult` models instead of raw Tavily responses, keeping the rest of the pipeline independent of the search provider.
- Supports configurable domain allowlisting through `TRUSTED_DOMAINS` in `settings.py`.
- Validates user input before making external API requests.
- Translates Tavily-specific exceptions into project-specific exceptions, preventing SDK details from leaking into the rest of the application.

## Fetch Articles Tool

### Pipeline Position

```text
Web Search
      │
      ▼
Fetch Articles          ← This tool
      │
      ▼
Extract Facts           
      │
      ▼
Fact Check
      │
      ▼
Generate Report
```

### Why `httpx` + `trafilatura`?

- `httpx` provides an async HTTP client that integrates naturally with the async-first architecture.
- `trafilatura` is responsible only for extracting the main article content from HTML after it has been fetched.

This keeps ownership of the retrieval pipeline while delegating HTML boilerplate removal (navigation bars, ads, footers, etc.) to a mature library.

**Tradeoff**

| Option | Pros | Cons |
|--------|------|------|
| `trafilatura` ✅ | Robust article extraction, less boilerplate, focuses project on orchestration | Doesn't teach HTML extraction algorithms |
| `BeautifulSoup/regex`❌ | Learn HTML parsing internals | Large amount of parsing code unrelated to the project's learning goals |

Implements HTTP fetching, validation, content-type checking, size limits, and error handling itself.

---

### Why stream responses instead of downloading everything?

Articles are downloaded using `httpx.AsyncClient.stream()` instead of loading the entire response into memory.

The tool performs two layers of protection:

1. Check the `Content-Length` header (when available) before downloading.
2. Stream the response in chunks and stop immediately if the accumulated size exceeds the configured limit.

This prevents unnecessarily downloading very large pages and also protects against servers that omit or misreport the `Content-Length` header.

---

### Exception translation pattern

Translated http-specific exceptions into project-specific exceptions. This keeps the rest of the research pipeline independent of the HTTP library

---

## Extract Facts Tool

### Pipeline Position

```text
Web Search
      │
      ▼
Fetch Articles
      │
      ▼
Extract Facts           ← This tool
      │
      ▼
Fact Check
      │
      ▼
Generate Report
```

---

### Overview

The **ExtractFactsTool** is the reasoning stage of the research pipeline. It receives fully extracted article content (`List[ArticleContent]`) from the previous stage and uses an LLM to convert unstructured text into structured factual claims (`List[ExtractedFact]`). :contentReference[oaicite:0]{index=0}

Unlike the search and article-fetching stages, this tool performs semantic reasoning rather than simple data retrieval. The output is later consumed by the fact-checking stage.

---

Input:

- `List[ArticleContent]`

Output:

- `List[ExtractedFact]`

---

### 1. Process Articles Individually

Each article is processed in its own LLM request instead of batching multiple articles together. :contentReference[oaicite:1]{index=1}

**Why**

- Keeps source attribution simple (every extracted fact knows exactly which article it came from)
- One failed article does not affect the rest of the batch
- Avoids unnecessarily large prompts
- Easier logging and debugging

Example:

```text
Article A  ──► LLM ──► Facts A

Article B  ──► LLM ──► Facts B

Article C  ──► LLM ──► Error
                    │
                    ▼
                Skip article

Final Output:
Facts A + Facts B
```

This follows the pipeline philosophy of **graceful degradation** rather than failing the entire workflow because of one bad input.

---

### 2. Use Function Calling Instead of Prompting for JSON

Rather than asking the model:

> "Return valid JSON."

the tool forces the model to call an OpenAI-compatible function named `extract_facts`. The schema defines the exact structure expected from the model. :contentReference[oaicite:2]{index=2} :contentReference[oaicite:3]{index=3}

Example schema:

```python
extract_facts(
    facts=[
        {
            "statement": "...",
            "extraction_confidence": 0.95,
            "evidence": "..."
        }
    ]
)
```

**Why**

Function calling is significantly more reliable than prompt-only JSON because it prevents common formatting problems such as:

- Markdown code fences
- Extra explanations
- Invalid JSON
- Missing fields

The LLM is constrained to produce structured arguments matching the schema.

---

### 3. Force Tool Usage

The request is sent with:

```python
tool_choice="required"
```

instead of:

```python
tool_choice="auto"
```

This guarantees the model must invoke the extraction function rather than replying with plain text. :contentReference[oaicite:4]{index=4}

This makes downstream parsing much simpler because the tool always expects a function call.

---

### 4. Parse Tool Calls Instead of Free Text

After the LLM responds, the tool extracts the function arguments and converts them into Python objects. :contentReference[oaicite:5]{index=5}

Pipeline:

```text
LLM Response
      │
      ▼
tool_calls
      │
      ▼
arguments JSON
      │
      ▼
Python dictionaries
      │
      ▼
ExtractedFact models
```

This keeps the boundary between the LLM and the application strongly typed.

---

### 5. Retry Probabilistic Failures

One production issue discovered during development was malformed function calls.

Example:

```xml
<function=extract_facts>
{
    "facts": [...]
}
</function>
```

The JSON itself was correct, but the XML wrapper violated the OpenAI function-calling protocol, causing Groq to reject the request.

This failure is **probabilistic**, meaning the model may produce valid output on a subsequent attempt.

Therefore the client retries:

- Attempt 1
- Attempt 2
- Attempt 3

using exponential backoff before giving up.

---

### 6. Do Not Retry Deterministic Failures

Large articles occasionally exceeded the model's context window.

Example:

```text
HTTP 413
Request too large
```

Retrying will never make the article smaller.

Instead the article is skipped and processing continues.

This distinction between **probabilistic** and **deterministic** failures greatly improves reliability.

---

### 7. Graceful Degradation

Errors affecting one article never stop the entire pipeline. :contentReference[oaicite:6]{index=6}

Examples:

- malformed response
- timeout
- rate limit
- context window exceeded

Result:

```text
Article 1 ✓
Article 2 ✓
Article 3 ✗
Article 4 ✓

Pipeline continues.

Output contains facts from Articles 1, 2 and 4.
```

This mirrors how production ETL and AI pipelines typically behave.

---

### Failure Modes

| Failure | Cause | Domain Exception | Retry? |
|---------|-------|------------------|--------|
| Rate limit | HTTP 429 | `ExternalAPIRateLimitError` | ✅ Yes |
| Timeout | Network/API | `ExternalAPITimeoutError` | ✅ Yes |
| Malformed tool call | Invalid function arguments | `MalformedResponseError` | ✅ Yes |
| Context window exceeded | HTTP 413 | `ContextWindowExceededError` | ❌ No |
| Invalid request | HTTP 400 | `InputValidationError` | ❌ No |

---

### Current Limitations

Large articles are currently skipped rather than chunked.

Future improvements could include:

- chunking large articles into smaller sections
- merging facts extracted from multiple chunks
- supporting larger-context models
- automatic chunk overlap for improved context preservation

These optimizations were intentionally deferred to keep the initial implementation focused and maintainable.

---

### Key Takeaways

Building this tool highlighted several important production lessons:

- Function calling is substantially more reliable than prompt-only JSON generation.
- LLM failures are not all the same—probabilistic failures should often be retried, while deterministic failures should fail fast.
- Graceful degradation is preferable to aborting an entire pipeline because of one problematic article.
- Separating retry logic (LLM client) from business logic (tool implementation) results in cleaner, more maintainable code.

---

Testing revealed an important limitation of **`llama-3.1-8b-instant`** when performing structured tool calling.

Although malformed tool calls (`tool_use_failed`) are classified as **retryable**, retries do not always recover the request. In testing, one article consistently failed all three retry attempts due to the model repeatedly generating an XML-style function wrapper instead of the OpenAI-compatible tool call format expected by Groq.

The pipeline behaves as designed:

- Retries malformed responses with exponential backoff.
- Logs the failure after the final retry.
- Skips the failed article.
- Continues processing the remaining articles.

This demonstrates graceful degradation rather than pipeline failure.

**Takeaway:** Smaller open-weight models can exhibit a relatively high failure rate on strict function-calling tasks. Increasing `max_retries` may improve success rates at the cost of additional latency, while upgrading to a more capable model would likely reduce these failures.

---

## Logging Improvements

**Decision:** Suppress verbose third-party DEBUG logs while preserving DEBUG logging for the application's own code.

**Why?**

Configuring the root logger at `DEBUG` also enabled debug logging from dependencies such as `httpx`, `httpcore`, `openai`, `trafilatura`, and `readability-lxml`. These libraries produced hundreds of low-level networking and parsing messages that obscured the application's own retry logic and pipeline events.

Instead of lowering the global log level, the project explicitly raises the log level of known noisy libraries to `WARNING`, allowing:

- Clean, readable logs during development
- Full DEBUG visibility for application code
- Easier debugging of retries, tool execution, and pipeline flow

```python
NOISY_LOGGERS = [
    "httpx",
    "httpcore",
    "openai",
    "trafilatura",
    "readability-lxml",
]
```

This list is intentionally hardcoded in `logger.py` because it reflects implementation details of project dependencies rather than application configuration.

---

## Decision: Remove Fact-Checking Stage

**Decision:** Remove the `FactCheckTool` from the research pipeline.

**Why:** The project's goal is to learn AI engineering patterns (tool orchestration, retrieval, structured LLM outputs, retries, and exception handling). Adding a fact-checking stage would require another round of LLM calls, significantly increasing latency, token usage, and rate-limit pressure on the free Groq tier while providing relatively little additional learning value.

**Tradeoff:** The final report now uses **extraction confidence** rather than independently verified confidence. This limitation is documented and can be addressed in a future version with a stronger model or dedicated verification pipeline.

---

## Agent Orchestration

**Decision:** Introduce a dedicated `ResearchAgent` to orchestrate the complete research pipeline and centralize report generation, while improving resilience to real-world API failures observed during integration.

### Why

Individual tools are responsible for only one task (search, fetch, or fact extraction). The orchestration layer coordinates the workflow, assembles the final report, and handles failures between stages without coupling the tools together.

### Pipeline

```
User Query
    │
    ▼
Web Search
    │
    ▼
Fetch Articles
    │
    ▼
Extract Facts
    │
    ▼
Build Sources & Findings
    │
    ▼
Generate Summary
    │
    ▼
Research Report
```

### Key Design Decisions

- Added a dedicated `ResearchAgent` responsible for coordinating the pipeline.
- Reused the existing `GroqLLMClient` from `ExtractFactsTool` for summary generation instead of creating a second LLM client.
- Summary generation uses a normal chat completion (no tool calling), since the desired output is natural-language prose rather than structured data.
- Overall report confidence is computed as the mean extraction confidence of all findings.
- Internal pipeline models (`ArticleContent`, `ExtractedFact`) are mapped into API-facing models (`Source`, `Finding`, `ResearchReport`) only at the orchestration layer.

### Graceful Degradation

The agent exits early whenever a stage produces no usable output:

- No search results → empty report.
- No articles fetched → empty report.
- No facts extracted → empty report.
- Summary generation failure → return the report with a fallback summary instead of failing the entire request.

This allows partial failures to degrade gracefully while still returning a valid API response whenever possible.

### Production Issues Discovered

During end-to-end integration, several real API behaviors required additional handling.

#### 1. Groq "reduce the length" errors

Groq sometimes returns oversized requests as an HTTP 400 with a `"reduce the length"` message instead of the expected HTTP 413.

**Decision:** Detect this observed message pattern and translate it into `ContextWindowExceededError`.

This keeps all context-window failures following the same handling path (warning + skip article) regardless of how the API reports them.

#### 2. Blocked article requests

Some websites (e.g. Reuters) returned HTTP 401 instead of HTTP 403 when denying automated access.

**Decision:** Treat both HTTP 401 and HTTP 403 as `BlockedRequestError`.

Both responses represent the same outcome from the application's perspective: the article cannot be accessed and should be skipped.

#### 3. Exception classification

Without the new context-window mapping, oversized requests were incorrectly classified as `InputValidationError`, which was then wrapped as an `UnexpectedError` inside the extraction tool.

**Decision:** Normalize these API responses into `ContextWindowExceededError` so expected operational failures are logged as warnings and skipped instead of appearing as unexpected application errors.

### Benefits

- Clear separation between orchestration and tool responsibilities.
- Single entry point for the complete research workflow.
- Graceful handling of partial failures.
- Consistent domain exception hierarchy despite inconsistent third-party API behavior.
- More robust production behavior based on real integration testing rather than documented API assumptions.

---

### Decision: Source Filtering

**Decision:** Only include sources in the final report if they contributed at least one extracted finding.

**Why:** Successfully fetching an article does not guarantee successful fact extraction. LLM tool-calling can fail probabilistically (e.g., malformed tool calls after all retries), resulting in articles that were fetched but produced no usable findings. Listing these as report sources would be misleading.

**Observed Behavior:** During testing, the same article (Simple English Wikipedia: Giant Panda) succeeded in one run but failed all three extraction retries in a subsequent run without any code changes. This demonstrates the probabilistic nature of the model's tool-calling reliability. The report now correctly distinguishes:
- `sources_fetched`: articles successfully fetched and sent for extraction.
- `sources`: only articles that actually contributed findings.

---