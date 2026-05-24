# Tanger Med · CIRES Technologies — RAG Knowledge Assistant

A bilingual (French / English) Retrieval-Augmented-Generation assistant that answers questions over a public corpus of **Tanger Med Group** and **CIRES Technologies** documents (annual reports, financials, CSR reports, brochures, press releases).

Built as a technical challenge for the **AI Engineer** position at CIRES Technologies (Tanger Med Group subsidiary).

---

## TL;DR — What it does

You ask questions in French or English. The system:

1. **Detects** intent and language with GPT-4o-mini, rewriting follow-up questions into stand-alone retrieval queries.
2. **Retrieves** the most relevant chunks from a Weaviate vector index using **hybrid search** (BM25 + dense vectors, multilingual embeddings via OpenAI `text-embedding-3-small`).
3. **Generates** a grounded answer with GPT-4o, citing every fact back to the source PDF and page number — no hallucinations.
4. **Logs** every step (intent, retrieval, generation) to a PostgreSQL audit trail visible in an admin dashboard.
5. **Escalates** low-confidence or human-requested turns to a review queue.

Example: *"Quel a été le trafic conteneurs de Tanger Med en 2024 ?"* → *"Tanger Med a traité 10 241 392 conteneurs en 2024, soit une hausse de 18,8 % par rapport à 2023 [#1]"* — with a clickable citation to the 2024 Port Activity Report, page 3.

---

## Why this design (and not just a vanilla LLM call)

| Decision | Why |
| --- | --- |
| **Hybrid retrieval** (BM25 + vector) | Pure vector search misses exact numeric phrases ("11.23 billion MAD"). Pure BM25 misses paraphrased questions. Hybrid gets both. |
| **Citation-first prompt** | The system prompt requires `[#N]` citations for every factual claim. If the model can't ground a claim, it says so honestly instead of guessing. |
| **Page-number-aware chunks** | Each chunk stores its page number, so citations link the user back to a specific PDF page — auditable for a port operator. |
| **Per-step audit log** | Every conversation logs intent, query rewrite, retrieval scores, and final answer. Critical when a regulated business (port authority) needs to know *why* a system produced a given answer. |
| **Multilingual by design** | Tanger Med reports are FR + EN; CIRES press coverage is FR. The system detects user language and answers in it. Embedding model is multilingual. |
| **Honest "I don't know"** | When the retrieved context doesn't support an answer, the system refuses to fabricate — and offers related topics from the corpus instead. |
| **Admin dashboard** | Beyond the chat, a separate panel shows conversation history, confidence trends, retrieval traces, and an escalation queue for ops review. |

---

## Architecture

```
┌─────────────────────────┐
│  React chat UI (5173)   │  bilingual, citation chips
└───────────┬─────────────┘
            │ POST /api/chat
            ▼
┌─────────────────────────┐
│  FastAPI (8000)         │
│  ─ understand (4o-mini) │  intent / language / query rewrite
│  ─ route                │  no_search | search | escalate
│  ─ retrieve (Weaviate)  │  hybrid BM25 + vector, top-K
│  ─ generate (GPT-4o)    │  grounded reply with [#N] citations
│  ─ audit (Postgres)     │  every step logged
└─────┬───────────┬───────┘
      │           │
      ▼           ▼
 ┌────────┐   ┌──────────┐
 │Weaviate│   │PostgreSQL│
 │ Chunks │   │ convs +  │
 │ 1536-d │   │ audit +  │
 │ + BM25 │   │ docs/chk │
 └────────┘   └──────────┘
```

### Tech stack

- **Backend** — FastAPI (async), SQLAlchemy 2.0, Pydantic 2
- **LLM** — OpenAI GPT-4o (synthesis), GPT-4o-mini (understand)
- **Embeddings** — OpenAI `text-embedding-3-small` (1536-d, multilingual)
- **Vector DB** — Weaviate 1.28 (hybrid BM25 + cosine)
- **Optional reranker** — Cohere `rerank-multilingual-v3.0` (off by default)
- **Database** — PostgreSQL 16 (conversations, messages, documents, chunks, audit logs)
- **Cache** — Redis 7
- **Frontend** — React 18 + Vite, plain CSS
- **PDF parsing** — PyMuPDF (`fitz`)
- **Infra** — Docker Compose

### Project layout

```
backend/
├── ai/
│   ├── agent.py           # orchestrator: understand → route → search → respond
│   ├── understand.py      # GPT-4o-mini step (intent + query rewrite)
│   ├── schemas.py         # Pydantic schemas (ConversationState, Citation, …)
│   └── prompts/
│       ├── system.txt     # bilingual grounded-answer prompt (FR/EN)
│       └── understand.txt # intent / language / query-rewrite prompt
├── api/
│   ├── chat.py            # POST /api/chat
│   ├── admin.py           # /api/admin/* (conversations, docs, escalations, stats)
│   └── routes.py
├── search/
│   ├── weaviate_client.py # hybrid search over Chunks collection
│   └── rerank.py          # optional Cohere reranking
├── documents/
│   ├── parser.py          # PyMuPDF page-by-page extraction
│   ├── chunker.py         # page-aware chunking with overlap
│   └── ingest.py          # download → parse → chunk → embed → store
├── db/
│   ├── models.py          # Conversation, Message, Document, Chunk, AuditLog
│   └── base.py
├── core/config.py         # Pydantic Settings (env-driven)
└── main.py                # FastAPI app + lifespan + health
frontend/
├── src/pages/             # ChatPage, AdminPage
├── src/components/chat/   # bubbles with citation chips
└── src/components/admin/  # StatsBar, ConversationList, EscalationQueue, DocumentsList
corpus/
├── manifest.json          # list of PDFs to ingest (URL + metadata)
└── pdfs/                  # downloaded PDFs (gitignored)
docker-compose.yml         # api, frontend, postgres, redis, weaviate, pgadmin, ingest
```

---

## Quick start

### 1. Configure

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### 2. Start the stack

```bash
docker compose up -d --build
```

This boots:

| Service       | URL                          |
| ------------- | ---------------------------- |
| Chat UI       | http://localhost:5173        |
| API           | http://localhost:8000        |
| API health    | http://localhost:8000/health |
| API docs      | http://localhost:8000/docs   |
| Admin board   | http://localhost:5173/admin  |
| pgAdmin       | http://localhost:5050        |
| Weaviate      | http://localhost:8080        |
| RedisInsight  | http://localhost:5540        |

### 3. Ingest the corpus

```bash
docker compose --profile cli run --rm ingest
```

This downloads the PDFs listed in `corpus/manifest.json`, extracts text page-by-page, chunks with overlap, embeds with OpenAI, and indexes the chunks in Weaviate (hybrid) and PostgreSQL.

To add documents, edit `corpus/manifest.json` and re-run the ingest command.

---

## Example questions

**French**
- *Quel a été le chiffre d'affaires de Tanger Med en 2024 ?*
- *Combien de conteneurs ont été traités en 2024 ?*
- *Quels sont les engagements RSE de Tanger Med ?*
- *Que fait CIRES Technologies ?*

**English**
- *What was Tanger Med's container throughput in 2024?*
- *How did 2024 compare to 2023 for container volume?*
- *What services does CIRES Technologies offer?*
- *What is Tanger Med's CSR strategy?*

For an out-of-corpus question, the assistant will honestly say it doesn't have that information and suggest topics it can answer.

---

## Corpus

The demo corpus is built from publicly available Tanger Med Group documents:

| Document | Year | Source |
| --- | --- | --- |
| Port Activity Report | 2024 | [Tanger Med Port](https://www.tangermedport.com/wp-content/uploads/2025/01/CP-TMPA-PORT-ACTIVITY-REPORT-IN-2024.pdf) |
| Port Activity Report | 2025 | [Tanger Med Press](https://www.tangermed.ma/wp-content/uploads/press-releases/2026/CP-TMPA-PORT-ACTIVITY-REPORT-IN-2025.pdf) |
| Rapport financier (FR) | 2024 | [Tanger Med Docs](https://www.tangermed.ma/wp-content/uploads/documentations/2025/rapport-financier-2024-V-WEB.pdf) |
| CSR Report | 2024 | [Tanger Med Docs](https://www.tangermed.ma/wp-content/uploads/2025/09/CSR-Report-2024.pdf) |

The corpus is configurable via `corpus/manifest.json` — adding a CIRES press kit, GITEX Africa coverage, or any other PDF just means appending an entry.

---

## What's intentionally NOT included

This is a focused demo for a one-day deliverable, so several "production" concerns are deliberately deferred:

- **No auth.** Anyone reaching the dashboard can see all conversations. Trivial to add with FastAPI Depends + JWT, out of scope here.
- **No OCR for scanned PDFs.** PyMuPDF extracts text from digitally-generated PDFs; scanned-image PDFs would need a Tesseract / Azure Document Intelligence pass.
- **Reranker disabled.** Cohere multilingual reranking is wired up but off by default to keep the demo dependency-light; flip `RERANK_ENABLED=true` to enable.
- **No streaming.** The reply is returned in one shot. Server-Sent Events / WebSocket streaming is straightforward to add but adds complexity.
- **No evaluation harness.** A production system would have a small held-out evaluation set with citation-accuracy metrics. Easy follow-up.

---

## Notes for the reviewer

This codebase was built from the architectural skeleton of a previous customer-service RAG project I worked on. The orchestration pattern (understand → route → retrieve → respond → audit) and the admin dashboard structure are reused; the corpus model, prompts, ingestion pipeline, and frontend branding are all new for this challenge.

I chose **Option 2 — RAG** because it lines up directly with CIRES Technologies' core value proposition (knowledge work over complex, multilingual industrial documentation), and because pointing the demo at *your own* publicly available documents made for a more memorable proof point than another wikipedia toy.

Happy to walk through any of the design choices live. — Hamza
