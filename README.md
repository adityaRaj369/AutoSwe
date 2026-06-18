



# AutoSWE — Autonomous Software Engineering Agent

> Takes a GitHub issue, autonomously explores the codebase, reasons about the root cause, writes a fix, verifies it by running tests, and opens a pull request. Production mode uses an OpenAI-compatible hosted model with JSON-mode action output; Ollama remains supported for embeddings and local-only experimentation. Built from scratch with **no agent frameworks** (no LangChain, no CrewAI). **Python backend (FastAPI).**

This is a Python implementation of the AutoSWE architecture: a from-scratch ReAct agent loop, a RAG code-search pipeline, a sandboxed execution environment, self-verification via tests, and a real-time React reasoning-trace dashboard.

---
x


https://github.com/user-attachments/assets/f68e549c-903a-47c0-a2d5-ec5ff8d96bed

https://github.com/user-attachments/assets/aaedae4d-565f-43a6-8dfe-076cb1672d21

## What's inside

| Layer | Technology |
|------|------------|
| API + webhooks | FastAPI + Uvicorn |
| Real-time | python-socketio (Redis-backed, cross-process) |
| Database | PostgreSQL + SQLAlchemy (async) + Alembic |
| Queue | arq (Redis) |
| Vector store | ChromaDB |
| Agent LLM | OpenAI-compatible JSON mode (`llama-3.3-70b-versatile` on GroqCloud by default) or optional Ollama local mode |
| Embeddings | Ollama `nomic-embed-text` |
| Sandbox | Docker (docker-py) with a local fallback |
| GitHub | App (JWT→installation token) or PAT, over httpx |
| Dashboard | React 18 + Vite + Tailwind + Recharts + Framer Motion + Socket.IO |

---

## Architecture

```
GitHub issue ──(webhook)──▶ FastAPI ──▶ arq queue ──▶ Agent Runtime
                                                          │
   ┌──────────────────────────────────────────────────────┘
   ▼
ReAct loop:  REASON (LLM) → ACT (tool) → OBSERVE (result)   ×25 max
   │  tools: search_code(RAG) grep read_file list_directory edit_file
   │         create_file run_command run_tests git_diff submit_solution
   │  runs inside a Docker sandbox (mem/CPU limited)
   ▼
self-verify (tests must pass) → push branch → open PR with auto description
   │
   └──▶ every step streamed over Socket.IO ──▶ React reasoning-trace dashboard
```

The ReAct loop lives in [`server/app/agent/runtime.py`](server/app/agent/runtime.py).

---

## Quick start

### Prerequisites
- Docker & Docker Compose
- 16GB+ RAM if running local Ollama embeddings/chat
- A GitHub PAT (quick start) or GitHub App (production)
- `LLM_API_KEY` for production-grade autonomous fixing

### Run the full stack

```bash
cp .env.example .env          # add GITHUB_PAT and LLM_API_KEY
docker compose up -d postgres redis chromadb ollama

# Pull models (one-time, several GB)
bash scripts/setup-ollama.sh

# Build the agent sandbox image
bash scripts/build-sandbox.sh

# Start backend, worker, and dashboard
docker compose up -d server worker client
```

- Dashboard: http://localhost:5173
- API: http://localhost:3001 — health at `/api/health`

### Run locally (without Docker for the app code)

```bash
# Backend
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # or it auto-creates tables in dev
export SANDBOX_USE_LOCAL=true # run agent commands on host instead of Docker
uvicorn app.main:app --port 3001 --reload

# Worker (separate terminal)
arq app.queue.worker.WorkerSettings

# Dashboard (separate terminal)
cd client && npm install && npm run dev
```

### Try it
1. Open the dashboard → **Repositories** → connect `owner/repo` (indexing starts automatically).
2. Trigger a run by issue number, **or** install the GitHub App / point a webhook at `/api/webhook/github` and label an issue `autoswe`.
3. Open the run and watch the reasoning trace stream in real time.

Seed a demo run for screenshots:
```bash
cd server && python ../scripts/seed_demo.py
```

### Lightweight dashboard demo

Use this path when you only want to inspect the UI and existing run history without
pulling Ollama models or running a real agent job:

```bash
docker compose up -d postgres redis chromadb

docker build -t autoswe-server-demo ./server
docker run --rm -d --name autoswe-server-demo \
  --network autoswe_default \
  -p 3001:3001 \
  -e DATABASE_URL=postgresql+asyncpg://autoswe:autoswe@postgres:5432/autoswe \
  -e REDIS_URL=redis://redis:6379 \
  -e CHROMA_URL=http://chromadb:8000 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e NODE_ENV=development \
  -e CORS_ORIGINS=http://localhost:5173 \
  autoswe-server-demo

docker cp scripts/seed_demo.py autoswe-server-demo:/tmp/seed_demo.py
docker exec -e PYTHONPATH=/app autoswe-server-demo python /tmp/seed_demo.py

cd client
NPM_CONFIG_USERCONFIG=/tmp/autoswe-empty-npmrc npm install
VITE_API_URL=http://localhost:3001 VITE_SOCKET_URL=http://localhost:3001 \
  npm run dev -- --host 0.0.0.0
```

Then open http://localhost:5173.

The demo health endpoint may show `ollama=false` if Ollama is not running. That is
expected for the dashboard-only path.

### Full end-to-end agent test requirements

Before testing the real GitHub issue → fix branch → PR flow, complete these:

```bash
bash scripts/setup-ollama.sh
bash scripts/build-sandbox.sh
docker compose up -d postgres redis chromadb ollama server worker client
```

You also need either `GITHUB_PAT` or GitHub App credentials in `.env`. Without
GitHub credentials, AutoSWE can show the dashboard and demo runs but cannot clone
private repositories, push branches, or open pull requests.

For production webhook use, set `GITHUB_WEBHOOK_SECRET`. In production mode,
unsigned GitHub webhooks are rejected.

Recommended production LLM settings:

```bash
LLM_PROVIDER=openai-compatible
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_S=180
```

Local Ollama chat remains available for experimentation, but it is not the
recommended production path for autonomous bug fixing:

```bash
LLM_PROVIDER=ollama
OLLAMA_CHAT_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_CONCURRENCY=1
OLLAMA_TIMEOUT_S=180
```

### Current production-readiness status

The GitHub E2E path is designed to:

1. Fetch the real GitHub issue title/body.
2. Index the target deployment branch codebase.
3. Run the agent in a sandbox using the configured `LLM_PROVIDER`.
4. Require tests before `submit_solution`.
5. Apply the generated diff to a fresh clone.
6. Create a unique `autoswe/issue-<n>-<run>` branch.
7. Open a GitHub PR.
8. Mark the run failed if PR creation fails.

Merging is intentionally left to GitHub review/permissions.

Jira/ClickUp ingestion is not part of the current code path yet; add it as a
separate connector service that creates the same internal `Run` records used by
GitHub/manual triggers.

---

## How it works

### 1. RAG code search
On connect, the repo is cloned, walked (skipping `node_modules`, lockfiles, binaries), and chunked **function-level** (Python via `ast`; other languages via declaration heuristics with a 100-line/20-overlap sliding-window fallback). Each chunk is embedded with `nomic-embed-text` and stored in ChromaDB (cosine). The agent's `search_code` tool embeds the query and returns the top-10 nearest chunks. See `server/app/indexer/`.

### 2. The ReAct loop
Each turn the LLM is given the system prompt, the issue, and the trajectory so far, and must emit a structured action. In production, OpenAI-compatible JSON mode returns `{"thought": "...", "action": {"tool": "...", "args": {...}}}` so invalid tool output is greatly reduced. The runtime still validates every action, fails fast on repeated protocol failures, and never merges code automatically.

### 3. Context management
First N steps are kept verbatim. When the trajectory exceeds the token budget, the middle steps are summarized by the LLM into one dense paragraph while the first 3 and last 7 steps are preserved (`server/app/agent/context_manager.py`).

### 4. Sandboxed tools
Tools run inside a per-issue Docker container with memory/CPU limits. `edit_file` requires the target text to appear **exactly once**; `run_command` blocks destructive patterns; `run_tests` auto-detects the runner (npm / pytest / maven / go). A `LocalSandbox` fallback exists for environments without a Docker daemon (`SANDBOX_USE_LOCAL=true`).

### 5. Self-verification + PR
`submit_solution` re-runs the suite and refuses to submit on failure. The captured diff is applied to a fresh clone, committed to `autoswe/issue-<n>`, pushed, and a PR is opened with an auto-generated description (root cause, files changed, key decisions, baseline vs. final tests).

---

## Project layout

```
autoswe/
├── server/            # Python backend (FastAPI)
│   ├── app/
│   │   ├── agent/     # ReAct loop, LLM client, parser, context mgmt, prompts
│   │   ├── indexer/   # clone, walk, chunk, embed, ChromaDB store (RAG)
│   │   ├── tools/     # 10 agent tools + registry
│   │   ├── sandbox/   # Docker + local sandbox managers
│   │   ├── github/    # client, webhook, PR creator + description
│   │   ├── queue/     # arq config, processor (end-to-end), worker
│   │   ├── db/        # SQLAlchemy models, schemas, CRUD
│   │   ├── api/       # runs, repositories, health, webhook routers
│   │   ├── realtime/  # Socket.IO server + emitter
│   │   └── main.py    # FastAPI + Socket.IO bootstrap
│   ├── alembic/       # migrations
│   └── tests/         # pytest suite
├── client/            # React + Vite dashboard
├── scripts/           # ollama pull, sandbox build, demo seed
└── docker-compose.yml
```

---

## REST API

```
POST   /api/webhook/github           GitHub webhook receiver
GET    /api/runs                     List runs (paginated, filterable)
GET    /api/runs/{id}                Run detail with all steps
GET    /api/runs/stats               Aggregate stats
POST   /api/runs/manual              Manually trigger a run {repo_id, issue_number}
GET    /api/repositories             List repos
POST   /api/repositories             Connect a repo {owner, name}
POST   /api/repositories/{id}/reindex
PATCH  /api/repositories/{id}/config
GET    /api/health                   DB / Redis / agent LLM / Ollama / ChromaDB
```

Socket.IO: connect, `subscribe {run_id}`, receive `agent:step` and `run:complete`.

---

## Tests

```bash
cd server
SANDBOX_USE_LOCAL=true pytest -q
```

Covers the response parser (format robustness), the chunker (AST + fallback),
`edit_file` (exact / multi-match guards), the test-summary parser, and the
context manager's truncation + compaction. It also covers production safeguards
for manual GitHub issue fetching, webhook signature enforcement, Chroma/Ollama
indexing stability, PR patch application, and PR failure status handling.

---

## Notes
- Production reliability requires a hosted agent model. Local Ollama chat is supported but should be treated as experimental for full autonomous PR generation.
- Built without LangChain/CrewAI: prompt construction, trajectory management, and tool dispatch are all explicit and inspectable.
- Model recommendations: `deepseek-coder-v2:16b` (best), `qwen2.5-coder:14b`, `codellama:13b`. Embeddings: always `nomic-embed-text`.
# AutoSwe
