# Incident Copilot

An AI assistant for on-call engineers. Describe a production incident in plain English and it finds the relevant runbooks, works out the most likely cause, and returns the diagnostic steps, resolution steps and whether to escalate, as structured JSON with citations.

Built with **FastAPI**, **PostgreSQL + pgvector**, and **local LLMs via Ollama**, so it runs entirely on a laptop at zero cost. The embedding and LLM layers are provider-agnostic, and **AWS Bedrock** is supported as a drop-in alternative.

> **Status:** retrieval-augmented generation (RAG) pipeline complete: ingestion, semantic search and structured triage. Next up: an evaluation set, then agentic tool-calling. See [Roadmap](#roadmap).

---

## Example

```bash
curl -s localhost:8000/triage \
  -H "Content-Type: application/json" \
  -d '{"incident": "Checkout API returning intermittent 500s since the 2pm deploy. Logs show timeout waiting for connection. DB CPU looks normal."}'
```

```json
{
  "summary": "Most likely Database Connection Pool Exhaustion because the API is timing out with connection pool errors and the database metrics look normal.",
  "likely_causes": [
    {
      "cause": "Connection leak — code path that acquires a connection but doesn't release it on error",
      "confidence": "high",
      "runbook": "Database Connection Pool Exhaustion"
    },
    {
      "cause": "Pool size configured too small for current traffic volume",
      "confidence": "medium",
      "runbook": "Database Connection Pool Exhaustion"
    }
  ],
  "diagnostic_steps": [
    "Check current active vs idle connections in the pool metrics/dashboard",
    "Query the database for long-running or idle-in-transaction queries",
    "Review recent deploys for changes touching data access code",
    "Check application logs for repeated connection acquisition without matching release"
  ],
  "resolution_steps": [
    "If a specific query is hanging, kill it manually and identify the offending code path",
    "If it's a leak, roll back the most recent deploy touching data access code",
    "As a short-term mitigation, increase pool size if traffic genuinely outgrew it",
    "Add/verify connection timeout and proper try/finally (or context manager) release patterns"
  ],
  "escalate": false,
  "sources": [
    { "runbook": "Database Connection Pool Exhaustion", "section": "Symptoms", "score": 0.7409 },
    { "runbook": "Third-Party API Timeout Cascade", "section": "Diagnostic Steps", "score": 0.6818 }
  ],
  "model": "ollama/qwen2.5:7b"
}
```
*(trimmed for length)*

---

## How it works

```mermaid
flowchart LR
    subgraph Ingestion["Ingestion (scripts/ingest.py)"]
        RB[runbooks/*.md] --> CH[Split by ## section]
        CH --> EM1[Embed each chunk]
        EM1 --> DB[(Postgres + pgvector)]
    end

    subgraph Triage["POST /triage"]
        Q[Incident description] --> EM2[Embed query]
        EM2 --> VS[Top-k cosine search]
        DB --> VS
        VS --> RANK[Pick top 3 runbooks]
        RANK --> FULL[Fetch full runbooks]
        FULL --> LLM[LLM with JSON schema]
        LLM --> VAL[Validate + check citations]
        VAL --> OUT[Structured response]
    end
```

1. **Ingestion.** Each runbook is split on its `##` headings (Symptoms, Likely Causes, Diagnostic Steps, Resolution Steps, Escalation), and each section is one chunk. Before embedding, each chunk is prefixed with its runbook title, so a section like "Escalation" still carries which incident it belongs to. Chunks are stored with a content hash, so re-running ingestion only re-embeds what changed.
2. **Retrieval.** The incident description is embedded and matched against every chunk using cosine similarity over an HNSW index.
3. **Context assembly.** Retrieved chunks are grouped by runbook. The top 3 runbooks are then fetched **in full** and given to the LLM, rather than scattered fragments (see [design decisions](#design-decisions)).
4. **Generation.** The LLM is constrained to a JSON schema. The `runbook` field on each cause is an enum of the retrieved titles, so the model can't cite a runbook it wasn't given.
5. **Validation.** Pydantic validates the output. Sources in the response come from the retrieval results, not from the model.

---

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2, pydantic-settings |
| Vector store | PostgreSQL 16 + pgvector (HNSW index, cosine distance), running in Docker |
| DB driver | psycopg 3 with a connection pool |
| Embeddings | `mxbai-embed-large` via Ollama (1024-dim); AWS Bedrock Titan Text Embeddings v2 also supported |
| LLM | `qwen2.5:7b` via Ollama, with schema-constrained JSON output |
| Language | Python 3.13 |

---

## Getting started

### Prerequisites
- Python 3.11+
- Docker Desktop (or OrbStack)
- [Ollama](https://ollama.com)
- About 16GB of RAM is recommended for the 7B model

### 1. Clone and install
```bash
git clone https://github.com/<your-username>/incident-copilot.git
cd incident-copilot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Start Postgres + pgvector
```bash
docker compose up -d
docker compose ps        # wait for "healthy"
```
The schema in `db/init.sql` is applied automatically on first start. The database is exposed on port **5433**, so it doesn't clash with a local Postgres on 5432.

### 3. Pull the local models
```bash
ollama pull mxbai-embed-large   # embeddings (~670MB)
ollama pull qwen2.5:7b          # LLM (~4.7GB)
```

### 4. Ingest the runbooks
```bash
python -m scripts.ingest
```
```
Embedder: ollama | 25 chunks from 5 runbooks
  + runbooks/db-connection-pool-exhaustion.md [0] Symptoms
  ...
Done: 25 embedded, 0 unchanged, 0 removed
```
Use `--force` to re-embed everything, for example after switching embedding model.

### 5. Run the API
```bash
uvicorn app.main:app --reload
```
Interactive docs: **http://localhost:8000/docs**

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service and database status |
| `GET` | `/search?q=...&k=5` | Raw semantic search over runbook chunks, with similarity scores |
| `POST` | `/triage` | Full triage: retrieval + LLM analysis. Body: `{"incident": "...", "k": 8}` |

```bash
curl localhost:8000/health
# {"status":"ok","db":"ok"}

curl "localhost:8000/search?q=api+timing+out+connection+pool+exhausted&k=3"
```

---

## Configuration

All settings come from environment variables or `.env` (see `.env.example`).

| Variable | Default | Options |
|---|---|---|
| `DATABASE_URL` | `postgresql://copilot:copilot@localhost:5433/incident_copilot` | |
| `EMBEDDER` | `fake` | `ollama`, `bedrock`, `fake` (deterministic random vectors for testing the pipeline offline) |
| `OLLAMA_EMBED_MODEL` | `mxbai-embed-large` | Any Ollama embedding model with 1024 dimensions |
| `LLM` | `ollama` | `ollama`, `fake` (fixed stub response) |
| `OLLAMA_CHAT_MODEL` | `llama3.2` | e.g. `qwen2.5:7b` (recommended), `qwen2.5:3b` for 8GB machines |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `AWS_REGION` | `eu-west-1` | Used when `EMBEDDER=bedrock` |

Switching provider is a config change plus `python -m scripts.ingest --force`. No code changes are needed.

---

## Design decisions

**Chunk by section, not by token count.** The runbooks already have a consistent structure, so each `##` section is a meaningful, self-contained unit. Splitting on headings keeps "Symptoms" and "Resolution Steps" separate, so a query about symptoms matches symptom text.

**Give the LLM whole runbooks, not top-k fragments.** The first version passed the 8 best-matching chunks straight to the LLM. They came from 3 different runbooks, and the model mixed diagnostic steps from one runbook with resolution steps from another. Chunk-level search is still used to *rank* runbooks, but the model now reads the top 3 in full, so every step it returns comes from a coherent source.

**Constrain citations with the schema.** Early outputs cited runbooks by slightly wrong names, which broke citation matching. The JSON schema sent to the model now restricts `runbook` to an enum of the retrieved titles, so the model *can't* produce an invalid citation. A server-side check remains as a safety net.

**Model size mattered more than prompt tweaks.** With identical code and prompt, `llama3.2` (3B) diagnosed the example incident as a third-party API timeout. It misread symptoms from a runbook as facts about the incident. `qwen2.5:7b` correctly identified connection pool exhaustion. This is the motivation for the evaluation set on the roadmap.

**Provider-agnostic from the start.** Embeddings and the LLM sit behind small interfaces (`app/embeddings.py`, `app/llm.py`), selected by config. This allowed development against a fake embedder before any model was available, a switch to free local models, and keeps Bedrock one config change away.

**Idempotent ingestion.** A unique key on `(source_file, chunk_index)` plus a SHA-256 content hash means re-running ingestion upserts only changed chunks and removes chunks from deleted or shortened runbooks.

---

## Project structure

```
incident-copilot/
├── app/
│   ├── main.py          # FastAPI app: /health, /search, /triage
│   ├── config.py        # Settings (pydantic-settings, reads .env)
│   ├── db.py            # psycopg connection pool with pgvector registered
│   ├── embeddings.py    # Embedder interface: Ollama, Bedrock, fake
│   ├── llm.py           # LLM interface: Ollama (JSON-schema output), fake
│   ├── search.py        # Vector search + full-runbook fetch
│   └── triage.py        # Prompt, schema, retrieval → LLM → validation
├── db/
│   └── init.sql         # pgvector extension, runbook_chunks table, HNSW index
├── runbooks/            # Markdown knowledge base
├── scripts/
│   └── ingest.py        # Chunk, embed and upsert runbooks
├── docker-compose.yml   # Postgres 16 + pgvector
└── requirements.txt
```

---

## Roadmap

- [x] FastAPI skeleton with health check
- [x] Postgres + pgvector in Docker
- [x] Section-based ingestion with change detection
- [x] Semantic search endpoint
- [x] Structured triage endpoint with constrained citations
- [x] Free local inference via Ollama
- [ ] **Evaluation set:** labelled incidents to measure retrieval and triage accuracy, and compare models and prompts
- [ ] Expand the runbook knowledge base (5 → 15–20), including deliberately overlapping topics
- [ ] **Agentic tool-calling:** let the model check service status, query logs and inspect recent deploys before diagnosing
- [ ] Tests and CI
- [ ] Deployment
