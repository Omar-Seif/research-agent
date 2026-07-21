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

