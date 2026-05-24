# Design Decisions

Every meaningful choice in this codebase, with the alternatives considered and the trade-offs that pointed to the choice we shipped. Where a decision is also a **known limitation**, it's flagged ⚠️ and the deferred work is captured in [LIMITS.md](LIMITS.md).

---

## 1. Why RAG, not fine-tuning?

**Chosen:** Retrieval-augmented generation with frozen base models (GPT-4o + GPT-4o-mini) and OpenAI embeddings.

**Alternatives considered:**

| Alternative | Why we rejected it |
| --- | --- |
| Fine-tune a base LLM on the Tanger Med corpus | Slow iteration, expensive (a few hundred USD per epoch on a 7B model), poor citation behavior, and worst of all: the corpus changes (new press releases, new annual reports). Every refresh would need re-training. |
| Stuff the entire corpus into the context window | Even with GPT-4o's 128k context, ingesting 184 chunks every turn costs ~$0.08/turn and adds latency. With more docs (the realistic case at a port operator) the math breaks fast. |
| Prompt the LLM with the whole corpus once, ask follow-ups | Same cost problem; doesn't solve citations. |

**Why RAG wins for THIS use case:**

- **Freshness** — adding a new document is one HTTP POST (live upload UI) or one manifest entry + re-run, no training.
- **Citations** — retrieval gives us the source chunk, which we hand to the LLM with a "must cite [#N]" instruction. Fine-tuning offers no equivalent.
- **Cost** — ~$0.001-0.005/turn at our scale, dominated by GPT-4o generation, not retrieval.
- **Auditability** — every step is loggable (retrieval scores, top chunks, generation reasoning). Crucial for a regulated business like a port authority.

---

## 2. Why hybrid search (BM25 + vector), not pure vector?

**Chosen:** Weaviate hybrid query, `alpha=0.65` (slight vector bias).

**The case for hybrid (and against pure vector):**

Pure vector search is great at paraphrase ("revenue" ≈ "chiffre d'affaires" ≈ "turnover") but terrible at exact numeric or named-entity matches. A query for "10,241,392 containers" against a vector index will return semantically-near chunks, but BM25 nails the exact-token match instantly.

A real example from this corpus:
- Query: *"What was Tanger Med's revenue in 2024?"*
- Pure vector top-1: a generic "Tanger Med Group consolidated results" chunk.
- BM25 top-1: a chunk literally containing `1.135 billion USD`.
- Hybrid: both, ranked together.

**Alternatives considered:**

| Alternative | Why we rejected it |
| --- | --- |
| Pure dense vectors | Misses exact figures, SKUs, named entities (above). |
| Pure BM25 | Misses paraphrases ("chiffre d'affaires" ↛ "revenue" without bilingual dictionaries). |
| Hybrid with `alpha=0.5` | Tested; gave slightly worse top-1 on numeric queries. |
| Hybrid with `alpha=0.8` | Tested; over-weighted semantic, lost named-entity matches. |

**`alpha=0.65` rationale:** Hand-picked after spot-checking the eval set. Future work: tune via grid search over the eval set.

---

## 3. Why these embeddings (`text-embedding-3-small`)?

**Chosen:** OpenAI `text-embedding-3-small`, 1536-d, multilingual.

**Alternatives considered:**

| Alternative | Pro | Con |
| --- | --- | --- |
| `text-embedding-3-large` (3072-d) | ~5% better on MTEB benchmark | 1.7× cost, 2× storage, marginal gain at our scale. |
| Cohere `embed-multilingual-v3.0` | Strong multilingual benchmark scores | Another API dependency, similar quality, harder to swap if we leave OpenAI. |
| Open-source `intfloat/multilingual-e5-large` | Free, runs on a GPU | Self-hosting an embedding service is a project of its own. Saved for v2. |
| `bge-m3` (multilingual, multi-vector) | State-of-the-art retrieval | Same self-hosting overhead. |

**Why `text-embedding-3-small` wins for a one-day demo:**
- ~$0.00002 per 1K tokens (negligible at our corpus size).
- 1536-d is a sweet spot — large enough to be expressive, small enough to be index-efficient.
- Officially multilingual (handles FR + EN without language-specific tuning).
- One API key already in `.env`.

---

## 4. Why this chunking strategy (page-aware, ~1400 chars, 200 overlap)?

**Chosen:** Per-page paragraph accumulation up to a `target_chunk_chars` ceiling, with `overlap_chars` of tail carried forward.

**The numbers, and why:**

- **`target_chunk_chars=1400`** ≈ 350 tokens. Small enough that 6 chunks fit comfortably in GPT-4o's prompt (~2.1k tokens of context plus the system prompt). Large enough to retain a complete paragraph of reasoning.
- **`overlap_chars=200`** ≈ 50 tokens. Prevents concept-splits at boundaries (a sentence like *"Container throughput in 2024 reached 10,241,392…"* won't be cut between chunks).
- **Page-aware** (don't merge across pages): citations refer to a **page number**, which only makes sense if each chunk stays on a single page. Cleaner UX for the user clicking through to verify.

**Alternatives considered:**

| Alternative | Why we rejected it |
| --- | --- |
| Fixed-window chunking (e.g. every 512 tokens) | Splits sentences mid-clause; page-number citations become ambiguous. |
| Sentence-level chunking | Loses paragraph context; retrieved chunks too narrow for the LLM to reason from. |
| Semantic chunking (split at heading boundaries) | The right answer long-term ⚠️ — see [LIMITS.md#semantic-chunking](LIMITS.md). Punted for tonight because PDF heading detection is fiddly across Tanger Med's varied report templates. |
| Sliding window with full overlap | More chunks → more index size → marginal retrieval gain. Diminishing returns. |

---

## 5. Why a two-model cascade (`GPT-4o-mini` for understand, `GPT-4o` for generate)?

**Chosen:** `gpt-4o-mini` (~$0.15/1M input) for the understand step, `gpt-4o` (~$2.50/1M input) for generation.

**The economics:**

| Step | Model | Why this model | Cost factor |
| --- | --- | --- | --- |
| Understand (intent + language + query rewrite) | `gpt-4o-mini` | A classification task with a strict JSON schema. Mini is ~16× cheaper and good enough; we saw zero misclassifications in the eval set. | 1× |
| Generate (grounded answer with citations) | `gpt-4o` | This is where quality matters: phrasing, citation discipline, refusal behavior. GPT-4o is materially better at following the "cite [#N] or refuse" instruction. | ~16× |

**Alternative considered: single-model**
- "Just use GPT-4o for everything." → Costs ~2× per turn for marginal quality gain on the understand step.
- "Just use GPT-4o-mini for everything." → Tested; mini is noticeably worse at *refusing honestly* — it tends to fabricate when context is weak.

**Verdict:** the cascade saves ~50% per turn at no measurable quality loss.

---

## 6. Why citations are *required*, with honest refusal as the fallback?

**Chosen:** System prompt enforces `[#N]` citations on every factual claim; refusal if context insufficient.

The mechanism:
- Each retrieved chunk is shown to the LLM with a bracketed index (`[1]`, `[2]`, …) AND its `chunk_id`.
- The system prompt says: *"NEVER state a fact that is not directly supported by the retrieved context. ALWAYS attach citations. If the retrieved context does NOT contain the answer, say so honestly. NEVER invent figures, dates, or names."*
- The structured output schema includes a `cited_chunk_ids` array. The model must populate it with the **exact chunk_ids** of chunks it actually used.

**Why this matters for a port operator:**
- A wrong figure with no source = lawsuit risk.
- A right figure with a source = checkable.
- Both groundedness probes in our eval (`Who is the CEO of CIRES?`, `What is the current stock price?`) correctly returned refusals — zero fabricated citations.

**Alternatives:**
- "Cite at the end, free-form" — tested; the LLM cites only ~70% of claims and inconsistently. Inline `[#N]` is much more reliable.
- "Soft constraint (`prefer to cite`)" — quality drops to ~60% citation rate. The mandatory-or-refuse constraint is the lever.

---

## 7. Why Cohere reranking on top of hybrid search?

**Chosen:** Over-retrieve 20 candidates via hybrid search, then rerank with `rerank-multilingual-v3.0` down to 6.

**The case for a reranker:**

Hybrid search is a good *first-stage* but it has no notion of *the actual user question*. It scores chunk-vs-query similarity in embedding space and chunk-vs-query token overlap. A cross-encoder reranker (which Cohere's rerank-v3 is under the hood) jointly attends to query AND chunk, producing a more precise relevance score.

In practice on this corpus: the top-3 chunks are usually the same with or without reranking, but the chunks at ranks 4-6 are noticeably better after reranking (the financial chunk for a financial question, vs a tangentially related ESG chunk).

**Alternatives:**

| Alternative | Why we rejected it |
| --- | --- |
| No reranker | Leaves quality on the table when we already have a Cohere key. |
| Local cross-encoder (e.g. `ms-marco-MiniLM-L-6-v2`) | Faster (no network hop), but English-only and we need FR support. ⚠️ A multilingual local cross-encoder is a v2 candidate. |
| LLM-as-reranker (ask GPT-4o to score chunks) | Way too expensive (N chunks × 1 LLM call). |

**Tunable knob:** `RERANK_ENABLED=false` in `.env` disables it for a comparison run. Useful for showing the ablation.

---

## 8. Why Weaviate over pgvector / Chroma / Pinecone?

**Chosen:** Weaviate 1.28 in Docker, anonymous access, single-node.

**Alternatives considered:**

| Alternative | Pro | Con |
| --- | --- | --- |
| **pgvector** (Postgres extension) | Single-DB story; ACID transactions on vectors | No native BM25; would need to add it via tsvector or external library. Hybrid query becomes a custom SQL JOIN with ranking math. |
| **Chroma** | Simplest API, in-process is trivial | No native hybrid search at the time of writing; weaker production story; smaller ecosystem. |
| **Pinecone** (managed) | Zero ops; great UX | Paid, requires network; for a one-day demo, self-hosting is fine and more impressive. |
| **Qdrant** | Strong hybrid story; Rust-fast | Similar capabilities to Weaviate; I happened to be more fluent in Weaviate's GraphQL hybrid query syntax for this task. |
| **Milvus** | Massive-scale | Heavy ops footprint; overkill at our scale. |

**Why Weaviate wins for THIS demo:**
- Native hybrid search (BM25 + vector with a single `alpha` knob) — exactly what we wanted.
- Self-hostable, runs in Docker Compose alongside the rest of the stack.
- The schema for our `Chunks` collection is plain JSON; ingest is one HTTP POST.

---

## 9. Why PostgreSQL for conversation state + audit trail (and not all in Weaviate)?

**Chosen:** Vectors in Weaviate, *everything else* in PostgreSQL.

**The reasoning:**
- Weaviate is great at vector search but mediocre at relational queries ("show me the last 20 conversations with confidence < 0.3").
- The audit trail is a relational dataset (conversations 1:N messages 1:1 audit_logs) with timestamp filters, joins, aggregations. SQL is the right tool.
- Documents and chunks live in both: PostgreSQL as the source of truth, Weaviate as the search index. They share UUIDs.

**Alternatives:**
- "Everything in Weaviate." Tested mentally; the admin dashboard's GROUP BY / aggregate queries would have been ugly.
- "Everything in pgvector." See section 8.

---

## 10. Why the admin dashboard (not just a chat box)?

**Chosen:** A separate admin route showing live stats, conversation history, per-turn audit, escalation queue, corpus browser with **live PDF upload**.

**The argument:**

Most candidates' RAG demos are a chat box. That's table stakes. What signals engineering depth to a senior reviewer is everything *around* the chat:
- **Audit trail** — every step (intent, query rewrite, retrieval scores, generation reasoning) is queryable per-turn. This is how you'd debug a regression in production.
- **Escalation queue** — surfaces low-confidence turns for human review. Without this, the AI's mistakes silently disappear.
- **Corpus browser** — shows what's actually indexed, with chunk counts. Builds operator trust.
- **Live PDF upload** — lets a reviewer hand the system a fresh document during the demo and ask questions about it within ~30 seconds. High-impact party trick.

---

## 11. Why the corpus choice (Tanger Med + CIRES Technologies docs)?

**Chosen:** Public documents from the actual organization the challenge is *from*.

This isn't a technical choice — it's a strategic one. The alternative was to point at a generic corpus (Wikipedia, arXiv, etc.) and demonstrate the pipeline. That demonstrates the *plumbing* but doesn't demonstrate *product thinking*.

By choosing the reviewer's own documents:
- The demo answers questions *the reviewer cares about* ("What was our revenue in 2024?") instead of toy questions.
- It signals that I researched the company before submitting.
- It creates a natural conversation starter in the interview ("here's how I picked the corpus...").

The downside is risk: if the system fabricates a wrong fact about their own company in front of them, it's worse than fabricating a wrong fact about Wikipedia. That's why the citations + honest-refusal architecture is non-negotiable here — it's the safety net that makes the strategic choice viable.

---

## 12. Why bilingual (FR/EN), not also Arabic?

**Chosen:** FR + EN. Arabic intentionally deferred. ⚠️

**Reasoning:**
- The Tanger Med corpus is published primarily in FR and EN. Arabic versions exist but are less consistently available.
- `text-embedding-3-small` is multilingual and handles Arabic fine in principle, but my system prompt and intent enum were designed around FR/EN behaviors.
- Adding Arabic would mean: (a) accepting Arabic queries (Pydantic enum change), (b) reasoning prompt changes for RTL phrasing, (c) more eval cases to validate.

Punted for tonight; capture in [LIMITS.md](LIMITS.md). Easy v2.

---

## 13. Why a deterministic router on top of the LLM-classified intent?

**Chosen:** GPT-4o-mini classifies intent; a small `_NO_SEARCH_INTENTS` set in `agent.py` deterministically decides whether to retrieve.

**Why not let the LLM decide?**
- LLM-driven routing is fine for prototypes but introduces noise. Deterministic routing is debuggable, testable, and free.
- The intent enum is small (6 values). Two of them (`greeting`, `off_topic`) clearly skip retrieval. One (`human_request`) triggers escalation. The remaining three (`question`, `follow_up`, `clarification`) all retrieve.
- Future expansion (e.g. *date_filter_question* → retrieve with a date filter on Weaviate) keeps the routing layer where it should be: in code, not in prompts.

---

## 14. Operational decisions

A few smaller choices worth noting for completeness:

- **Async PG (asyncpg)** for the chat path so we don't block the event loop on a 50ms DB roundtrip. Sync `psycopg2` for the ingest CLI script because it's simpler and ingestion is offline.
- **No host port binding for Postgres/Redis** in docker-compose to avoid colliding with the user's other dev containers. pgAdmin gives us inspection without exposing the DB.
- **`asyncio.to_thread`** for the live PDF upload endpoint, so the sync ingest pipeline doesn't block the async API.
- **`gen_random_uuid()` in PG vs Python-side UUID generation** — we use Python-side because the `pgcrypto` extension setup is one less thing to debug across environments.
- **A fresh `git init`** for this repo, no MHAM history. The architectural ancestry is in the README's *Notes for the reviewer* section, not in `git log`.

---

## How this would look at the next level of polish

See **[LIMITS.md](LIMITS.md)** for the full list. The headline candidates: semantic chunking, response streaming, an OCR pass for scanned PDFs, hybrid-weight tuning via grid search on the eval set, multi-doc citation diversity constraints, and per-organization access control.
