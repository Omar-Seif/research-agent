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