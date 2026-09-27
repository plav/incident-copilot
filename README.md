# Incident Copilot

An AI assistant for on-call engineers. Describe a production incident in plain English and it finds the relevant runbooks, works out the most likely cause, and returns the diagnostic steps, resolution steps and whether to escalate, as structured JSON with citations.

Built with **FastAPI**, **PostgreSQL + pgvector**, and **local LLMs via Ollama**, so it runs entirely on a laptop at zero cost. The embedding and LLM layers are provider-agnostic, and **AWS Bedrock** is supported as a drop-in alternative.

> **Status:** RAG pipeline complete and evaluated on two datasets: **88%** triage accuracy on a synthetic eval set, and **89% on real production incidents** from a live support team, with a free local 7B model. Next up: out-of-scope detection, then agentic tool-calling. See [Roadmap](#roadmap).

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
git clone https://github.com/plav/incident-copilot.git
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

**Model size mattered more than prompt tweaks.** With identical code and prompt, `llama3.2` (3B) diagnosed the example incident as a third-party API timeout. It misread symptoms from a runbook as facts about the incident. `qwen2.5:7b` correctly identified connection pool exhaustion. Across the full [eval set](#evaluation), that's 88% vs 59% triage accuracy, at roughly twice the latency.

**Provider-agnostic from the start.** Embeddings and the LLM sit behind small interfaces (`app/embeddings.py`, `app/llm.py`), selected by config. This allowed development against a fake embedder before any model was available, a switch to free local models, and keeps Bedrock one config change away.

**Idempotent ingestion.** A unique key on `(source_file, chunk_index)` plus a SHA-256 content hash means re-running ingestion upserts only changed chunks and removes chunks from deleted or shortened runbooks.

---

## Evaluation

`evals/incidents.json` holds 17 labelled incidents: three per runbook at easy, medium and hard difficulty, plus two out-of-scope incidents (an expired TLS certificate and a DNS outage) that no runbook covers. The hard cases deliberately use symptoms that overlap with other runbooks.

```bash
python -m scripts.eval --retrieval-only              # fast, no LLM
python -m scripts.eval                               # full triage
OLLAMA_CHAT_MODEL=llama3.2 python -m scripts.eval    # compare another model
```

**Metrics**
- **Retrieval hit@1 / hit@3:** is the expected runbook ranked first / in the top 3 by vector search?
- **Triage accuracy:** does the top likely cause cite the expected runbook? For out-of-scope incidents, a correct answer is one with no medium- or high-confidence cause.

**Results** (embeddings: `mxbai-embed-large`, 17 cases)

| | Qwen 2.5 7B | Llama 3.2 3B |
|---|---|---|
| **Triage accuracy** | **15/17 (88%)** | 10/17 (59%) |
| Easy / medium / hard | 5/5 · 6/6 · 3/4 | 3/5 · 4/6 · 3/4 |
| Out-of-scope | 1/2 | 0/2 |
| Avg time per triage (M-series MacBook Air, 16GB) | 29s | 15s |

Retrieval: **hit@1 13/15 (87%)**, **hit@3 14/15 (93%)**.

**What the numbers show**
- **The LLM step recovers retrieval mistakes.** On `api-03`, vector search ranked the wrong runbook first, but Qwen compared all three candidates and picked the right one. That's why the pipeline passes the top 3 runbooks instead of trusting the top hit.
- **Retrieval sets the ceiling.** On `oom-03`, the correct runbook wasn't in the top 3, so no model could answer correctly. Further gains there have to come from retrieval.
- **Out-of-scope detection is the weakest area.** Both models mapped the expired-certificate incident to an unrelated runbook with confidence.

### Real-world validation

The synthetic runbooks and incidents above were written for this project, so they're tidier than real ones. To test against the real thing, the pipeline was run on a **production support team's actual incident history**, entirely on a laptop with local models, so no data left the machine.

**Method**
1. **Runbooks from history.** The team's AI assistant (Atlassian Rovo) drafted four runbooks from a year of resolved incident tickets: pipeline out-of-memory failures, file ingestion failures, transaction-matching failures and missing-data query failures. Each one was reviewed before use.
2. **A time-based split to prevent leakage.** The runbooks were built only from tickets **older** than a cut-off date. The test set is **22 real incidents from the two months after it**, rewritten as the first report an engineer would see (symptoms and error messages, with the cause and all identifying details removed). The runbooks never saw these incidents.
3. **Out-of-scope cases.** Three of the 22 are recent incidents that fit none of the runbooks.

**Results** (`qwen2.5:7b`, `mxbai-embed-large`)

| | Result |
|---|---|
| **Real incidents: triage accuracy** | **17/19 (89%)** |
| Retrieval hit@1 / hit@3 | 16/19 (84%) · **19/19 (100%)** |
| Out-of-scope | 0/3 |
| Avg time per triage | 42s |

**Findings**
- **Consistent with the synthetic set.** 89% on real incidents vs 88% on synthetic ones, and in both the LLM step recovered retrieval misses. On real data, 2 of the 3 incidents that search ranked wrong were still triaged correctly, because the right runbook was in the top 3.
- **The eval surfaced a gap in a runbook, not just in the model.** One miss was an incident about records missing a field in matching output. The matching runbook never describes that symptom, but another runbook talks about "missing fields" a lot. The fix is to update the runbook. That's a useful side effect: if the copilot can't tell two runbooks apart, engineers probably struggle to as well.
- **Some misses are fair.** One incident's first report ("feeds failed during ingress") contained no clue to its real cause. An experienced engineer would likely have guessed the same wrong runbook.
- **Out-of-scope detection is the main weakness, confirmed on both datasets** (1/2 synthetic, 0/3 real). See below.

### Why a similarity threshold isn't enough

The obvious fix for out-of-scope incidents is to reject any incident whose best search score is below a threshold. The real-data scores show why that alone doesn't work:

```
0.525  out-of-scope   ← clearly lowest
0.585  real
0.592  real
0.592  out-of-scope   ← tied with a real incident
0.601  real
0.649  real
0.655  out-of-scope   ← higher than 4 real incidents
0.678+ all real
```

A threshold of ~0.55 catches one out-of-scope case safely. Any higher starts rejecting real incidents. One out-of-scope incident, a failing background job described in the same language as the pipeline incidents, outscores four real ones. **Similarity measures how much an incident *sounds like* a runbook, not whether the runbook actually covers it.**

The planned fix has two layers: a conservative threshold for the obvious cases, and an explicit "none of these fit" option for the LLM, which checks the incident against each runbook's Symptoms section before choosing.

### Running the eval on your own runbooks

Company runbooks and incidents go in `private/`, which is git-ignored:

```bash
# Split a pasted export of several runbooks into one file each (repairs lost headings)
python -m scripts.split_runbooks private/export.txt private/runbooks

python -m scripts.ingest --dir private/runbooks
python -m scripts.eval --cases private/incidents.json   # results saved to private/results/
```

Run `python -m scripts.ingest` afterwards to switch back to the sample runbooks.

Results for each run are saved to `evals/results/`.

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
├── evals/
│   ├── incidents.json   # Labelled test incidents
│   └── results/         # Saved eval runs
├── scripts/
│   ├── ingest.py        # Chunk, embed and upsert runbooks
│   ├── eval.py          # Score retrieval and triage against the eval set
│   └── split_runbooks.py # Split and repair a pasted multi-runbook export
├── private/             # Git-ignored: company runbooks, incidents and results
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
- [x] Evaluation set: 17 labelled incidents scoring retrieval and triage, with model comparison
- [x] Real-world validation: 22 held-out production incidents, 89% triage accuracy
- [ ] **Out-of-scope detection:** conservative similarity threshold plus an explicit "none of these fit" option for the LLM
- [ ] Improve retrieval on overlapping runbooks (query prefix for the embedding model, hybrid keyword + vector search)
- [ ] **Confluence and Jira loaders:** ingest runbooks from Confluence and surface similar past incidents from Jira
- [ ] **Knowledge-gap loop:** log out-of-scope incidents and draft new runbooks from them once resolved
- [ ] Expand the runbook knowledge base (5 → 15–20), including deliberately overlapping topics
- [ ] **Agentic tool-calling:** let the model check service status, query logs and inspect recent deploys before diagnosing
- [ ] Tests and CI
- [ ] Deployment
