# Maelstrom

AI-powered research workflow system for discovering research gaps and conducting paper-based Q&A.

Maelstrom covers the early stages of the research lifecycle — from identifying unexplored areas in a field to asking precise questions against a corpus of papers. The current V0 ships two core engines:

- **Gap Engine** — Input a research topic, get back an automated gap analysis powered by a LangGraph 8-node pipeline that searches arXiv, Semantic Scholar, OpenAlex, and OpenReview.
- **QA Chat** — Upload PDFs or share papers from Gap Engine, then ask questions with citation-backed answers via paper-qa.

## Quick Look

```
┌─────────────────────────────────────────────────────┐
│  Next.js Frontend (:3000)                           │
│  ┌───────────┐ ┌───────────┐ ┌──────────────────┐  │
│  │  /gap      │ │  /chat    │ │  /settings       │  │
│  │  Topic →   │ │  PDF ↑    │ │  LLM provider    │  │
│  │  Progress  │ │  Q&A ↕    │ │  API key         │  │
│  │  Results   │ │  Citations│ │  Model config     │  │
│  └───────────┘ └───────────┘ └──────────────────┘  │
│                      │ /api/* proxy                  │
├──────────────────────┼──────────────────────────────┤
│  FastAPI Backend (:8000)                             │
│  ┌────────────────┐  ┌───────────────────────────┐  │
│  │  Gap Engine     │  │  QA Chat (paper-qa)       │  │
│  │  LangGraph 8N   │  │  PDF → vectors → answers  │  │
│  │  4-source search│  │  with inline citations    │  │
│  └────────────────┘  └───────────────────────────┘  │
│                 SQLite (WAL mode)                     │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI · uvicorn · sse-starlette |
| AI Workflow | LangGraph (8-node directed graph) |
| Paper Q&A | paper-qa v5 (PDF parsing + vector retrieval) |
| Database | SQLite via aiosqlite (WAL mode) |
| Frontend | Next.js 16 · React 19 · TypeScript |
| UI | shadcn/ui · Tailwind CSS v4 · Base UI |
| Testing | pytest + pytest-asyncio / vitest |
| Linting | ruff (Python) · ESLint (TypeScript) |

## Prerequisites

- Python 3.10 – 3.12
- Node.js >= 18
- pnpm
- An LLM API key (OpenAI, Anthropic, or a local-compatible endpoint)

## Getting Started

### 1. Clone & install backend

```bash
git clone https://github.com/<your-org>/maelstrom.git
cd maelstrom

# Create a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install core dependencies
pip install -e .

# Install full dependencies (LangGraph, paper-qa, etc.)
pip install -e ".[full]"
```

### 2. Install frontend

```bash
cd frontend
pnpm install
cd ..
```

### 3. One-command start

```bash
npm start
```

This will:
1. Detect and kill any stale processes on ports 8000 / 3000
2. Start the FastAPI backend (`uvicorn` on `:8000`)
3. Start the Next.js frontend (`pnpm dev` on `:3000`)
4. Prefix all logs with `[backend]` / `[frontend]`
5. Write a `.maelstrom.pid` file for process tracking

Stop with `Ctrl+C` (graceful shutdown) or `npm stop` from another terminal.

### 4. Configure your LLM

Open [http://localhost:3000/settings](http://localhost:3000/settings) and enter your API key. Supported providers:

| Provider | Default Model |
|----------|--------------|
| OpenAI | gpt-4o |
| Anthropic | claude-sonnet-4-20250514 |
| Local | any OpenAI-compatible endpoint |

> API keys are stored in memory only — they are never written to disk.

## Usage

### Gap Engine

1. Navigate to [http://localhost:3000/gap](http://localhost:3000/gap)
2. Enter a research topic (e.g. *"transformer efficiency in edge deployment"*)
3. Watch the 8-step pipeline execute in real time via SSE:

```
topic_intake → query_expansion → paper_retrieval → normalize_dedup
→ coverage_matrix → gap_hypothesis → gap_critic → ranking_packaging
```

4. Browse retrieved papers, the coverage matrix, identified gaps, and ranked topic candidates

### QA Chat

1. Navigate to [http://localhost:3000/chat](http://localhost:3000/chat)
2. Upload PDFs or share papers from a Gap Engine run
3. Ask questions — answers come with inline citations pointing to specific passages

## Project Structure

```
maelstrom/
├── src/maelstrom/
│   ├── main.py              # FastAPI app entry point
│   ├── api/                  # Route handlers
│   │   ├── chat.py           #   /api/chat/*
│   │   ├── gap.py            #   /api/gap/*
│   │   ├── config.py         #   /api/config/*
│   │   ├── docs.py           #   /api/chat/docs/*
│   │   └── sessions.py       #   /api/sessions/*
│   ├── graph/                # LangGraph workflow
│   │   ├── gap_engine.py     #   8-node pipeline definition
│   │   ├── builder.py        #   Graph construction
│   │   └── nodes/            #   Individual node implementations
│   ├── adapters/             # Paper source adapters
│   │   ├── arxiv.py
│   │   ├── semantic_scholar.py
│   │   ├── openalex.py
│   │   └── openreview.py
│   ├── services/             # Business logic
│   │   ├── gap_service.py
│   │   ├── chat_service.py
│   │   ├── doc_service.py
│   │   └── paper_retriever.py
│   ├── schemas/              # Pydantic models
│   └── db/                   # SQLite database layer
├── frontend/
│   ├── app/                  # Next.js App Router pages
│   │   ├── gap/              #   Gap Engine UI
│   │   ├── chat/             #   QA Chat UI
│   │   └── settings/         #   LLM configuration
│   ├── components/           # React components
│   └── hooks/                # Custom hooks (useGapStream, useEventSource)
├── scripts/
│   ├── start.mjs             # One-command launcher
│   └── stop.mjs              # Process stopper
├── tests/                    # pytest test suite
├── docs/                     # Architecture & design docs
├── pyproject.toml            # Python project config
└── package.json              # npm scripts (start/stop)
```

## API Reference

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "ok"}` |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sessions` | Create a session |
| GET | `/api/sessions` | List sessions |
| DELETE | `/api/sessions/{id}` | Delete a session |

### Gap Engine

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/gap/run` | Start a gap analysis run |
| GET | `/api/gap/run/{id}/status` | Poll run status |
| GET | `/api/gap/run/{id}/stream` | SSE event stream |
| GET | `/api/gap/run/{id}/result` | Final result |
| GET | `/api/gap/run/{id}/papers` | Retrieved papers |
| GET | `/api/gap/run/{id}/matrix` | Coverage matrix |
| POST | `/api/gap/run/{id}/share-to-qa` | Share papers to QA index |

### QA Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat/ask` | Submit a question |
| GET | `/api/chat/ask/{id}/stream` | SSE answer stream |
| POST | `/api/chat/docs/upload` | Upload a PDF |
| GET | `/api/chat/docs` | List indexed documents |
| DELETE | `/api/chat/docs/{id}` | Remove a document |

### LLM Config

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config/llm` | Get current LLM config |
| PUT | `/api/config/llm` | Update LLM config |

## Development

### Run backend tests

```bash
pip install -e ".[dev]"
pytest
```

### Run frontend tests

```bash
cd frontend
pnpm vitest --run
```

### Lint

```bash
# Python
ruff check src/ tests/

# TypeScript
cd frontend && pnpm lint
```

## Architecture Notes

- **SSE over WebSocket** — All streaming uses Server-Sent Events for simplicity and native browser support.
- **No .env files** — API keys are configured at runtime through the Settings page and kept in memory only. Nothing sensitive touches disk.
- **SQLite + WAL** — Designed as a single-user local tool. The database uses WAL mode with foreign keys enabled for safe async access.
- **paper-qa in-process** — The QA engine runs inside the same Python process, no separate service or RPC needed.
- **V0 scope** — The current release uses a hardcoded `"default"` session. Multi-session support is wired in the backend but not yet exposed in the frontend.

## Roadmap

Maelstrom's full vision is a 5-layer, dual-axis research platform:

- **Horizontal engines**: Gap Engine (V0) → Synthesis Engine → Planning Engine → Experiment Engine
- **Vertical platform**: Workspace & Governance · Orchestration Runtime · Agent-Native Primitives (MCP Gateway, Skills Registry) · Data/Observability/Eval Foundation

See [`docs/`](./docs/) for detailed architecture documents.

## License

MIT