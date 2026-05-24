# Limits & Next Steps

A senior reviewer cares less about whether your demo is perfect and more about whether you *know where the gaps are* and have a plan. So: here's what this repo intentionally doesn't do, why it was deferred, and what we'd build next.

The deferrals are sorted roughly by impact-per-effort if I were to spend another day on this.

---

## 1. No automated evaluation beyond the golden set (highest priority next)

**What's there:** A 12-question golden set + a runner that scores retrieval-hit, keyword recall, confidence band, and groundedness. 12 / 12 currently pass.

**What's missing:**
- **Faithfulness** — is every claim in the answer actually supported by the cited chunk? A keyword match isn't the same as a logically-entailed answer. RAGAS or a small LLM-as-judge harness would do this.
- **Answer relevance** — does the reply actually answer the question (vs go on a tangent)?
- **Context precision / recall at K** — for each question, what fraction of the *retrieved* chunks were *relevant*?

**What we'd build next:**
- Add RAGAS to the eval pipeline. ~1 hour.
- Expand the golden set to 50+ questions across all 8 docs, with explicit `expected_chunk_id` (not just doc-title-substring). ~half-day with the corpus open.
- Wire eval results into CI: every code change runs the eval, fails on regression.

---

## 2. Chunking is page-aware fixed-size + overlap (semantic chunking deferred)

**What's there:** Per-page paragraph accumulation up to ~1400 chars with 200-char overlap.

**Why this is fine for now:** Tanger Med PDFs are paragraph-rich and structurally consistent (heading, body, table caption). Our eval shows 100% retrieval hit rate, so the chunker isn't a bottleneck right now.

**Why it would matter at scale:**
- For PDFs with rich heading hierarchies (e.g. an annual report with H1/H2/H3 sections), splitting at heading boundaries produces semantically tighter chunks.
- For very long tables, fixed-size chunking can split a table mid-row.

**What we'd build next:**
- Detect heading style runs in PyMuPDF (font-size + bold heuristic) and split at heading boundaries.
- Special-case table extraction (`page.find_tables()`) and emit table chunks with structured rows preserved.

---

## 3. No OCR for scanned PDFs

**What's there:** PyMuPDF text extraction. A scanned-image PDF would silently produce zero chunks.

**What we'd build next:**
- On parse, if `len(text_extracted) < 100` for a doc of more than 1 page, route to OCR.
- For OCR, the cheap default is `pytesseract` (offline). The high-quality choice is Azure Document Intelligence or AWS Textract. For a port operator with scanned customs forms etc., Document Intelligence is worth the cost.
- Acceptance test: pre-2010 Tanger Med press releases (some are scanned PDFs) should yield non-empty chunks.

---

## 4. No streaming response

**What's there:** The full reply is returned in one POST response (~4.5s end-to-end median).

**Why deferred:** A streaming endpoint touches three layers (FastAPI SSE, OpenAI streaming, React EventSource handling) and isn't strictly necessary to *demonstrate* correctness.

**What we'd build next:**
- FastAPI `StreamingResponse` over OpenAI's `stream=True`.
- Forward NDJSON events: `{type: "understand_done"}`, `{type: "search_done", scores: [...]}`, `{type: "token", delta: "Tanger..."}`, `{type: "citation", chunk_id: "..."}`, `{type: "done", confidence: 0.85}`.
- Frontend: existing `MessageBubble` accumulates the streamed text; citation chips render when the `citation` events arrive.

**Why this matters at scale:** subjective latency. Streaming makes a 5-second answer feel like a 1-second answer.

---

## 5. No caching layer

**What's there:** Redis is wired up but not actually caching anything (it was an MHAM-era message debouncer, now removed).

**What we'd build next:**
- **Embedding cache** — hash the chunk text + model, cache the embedding. Saves the embedding step entirely on re-ingest.
- **LLM response cache** — hash (system_prompt + retrieved_chunk_ids + user_message), cache the answer for a short TTL. Same question twice = instant second answer.
- **Cohere rerank cache** — same idea, hash (query + chunk_ids).

**Quick win:** the eval script re-runs the same 12 questions every time. With LLM cache hit, the second eval run drops from ~55s to ~5s.

---

## 6. No multi-doc citation diversity constraint

**What's there:** Top-6 reranked chunks can come from the same document.

**Why this matters:** For "What is Tanger Med?" — a broad question — the top-6 chunks shouldn't all be from one brochure. A diverse answer feels more grounded and gives the user multiple verification paths.

**What we'd build next:**
- Post-rerank, enforce a max-per-doc constraint (e.g. ≤2 chunks per document in the final top-6).
- Or use **maximum marginal relevance (MMR)** at retrieval time: pick chunks that are both relevant to the query AND dissimilar to already-picked chunks.

---

## 7. No conversational memory beyond a sliding window

**What's there:** Last 8 messages are passed verbatim to GPT-4o as conversation history.

**Why this is fine for short conversations:** Most demo turns are 1-3 exchanges deep.

**Why it breaks at scale:** After 30+ turns, you're either passing 30+ messages (cost + latency creep) or you're losing earlier context (forgetting that the user is asking about CSR, not financials).

**What we'd build next:**
- Periodic **conversation summarization**: every N turns, summarize the older messages into a compact "Conversation so far" block and replace them.
- Optional: **conversation-level retrieval** — older turns themselves become a tiny vector index, and we retrieve the relevant older turns instead of including all of them.

---

## 8. No multi-modal queries

**What's there:** Text questions only.

**What we'd build next:**
- Accept image uploads in the chat (a photo of a customs form, a screenshot of a financial table).
- Use GPT-4o vision to extract structured data from the image, then run the normal RAG flow over the extracted text.
- For a port operator: "Here's a screenshot of a manifest — what compliance flags apply?" is a real use case.

---

## 9. No authentication / RBAC

**What's there:** Anyone on `localhost` can hit the admin endpoints and the chat.

**Why deferred:** A one-day demo doesn't need auth and it would distract from the AI substance.

**What we'd build next for production:**
- **JWT auth** via FastAPI `Depends`, with a simple bcrypt-based user table in PostgreSQL.
- **Role-based access**: `viewer` can chat; `analyst` can browse conversations; `admin` can upload/delete documents.
- **Per-document ACLs**: enterprise corpora often have department-scoped documents.

---

## 10. Hybrid-weight `alpha=0.65` was picked by spot-check, not tuned

**What's there:** A single `alpha` knob on the Weaviate hybrid query.

**What we'd build next:**
- Grid search over the eval set: for `alpha ∈ {0.3, 0.5, 0.65, 0.8, 1.0}`, run the eval, pick the highest retrieval-hit-rate. Update `WEAVIATE_ALPHA` default to the winner.
- Could go further: per-query-type `alpha` (numeric question → BM25-heavy; conceptual question → vector-heavy).

---

## 11. Single-instance, no scaling story

**What's there:** Single docker compose stack, one of each service.

**What we'd build next for production:**
- Weaviate cluster (sharding + replication).
- PostgreSQL with read replicas for the admin dashboard.
- Stateless API workers behind a load balancer (the API is already stateless modulo the audit log writes).
- Background workers (Celery / Arq) for heavy ingestion jobs instead of `asyncio.to_thread`.

---

## 12. No metrics / tracing beyond the audit log

**What's there:** Per-turn audit rows in PostgreSQL with duration_ms per step.

**What's missing:**
- Latency percentiles (p50 / p95 / p99) per pipeline step over time.
- OpenTelemetry tracing across the understand → retrieve → rerank → generate flow.
- A Grafana / Looker dashboard for ops.

---

## Short list if I had ONE more day

1. **Faithfulness eval with RAGAS or LLM-as-judge** (catches subtle hallucinations the keyword test misses).
2. **Streaming responses** (perceived latency is the biggest UX win).
3. **Embedding + LLM caching** (cheap performance win, makes the eval ~10× faster).
4. **MMR for citation diversity** (improves broad-question answers).
5. **Auth on the admin dashboard** (table stakes before showing to anyone).

If I had one week, I'd also do semantic chunking, OCR for scanned PDFs, and Arabic support.
