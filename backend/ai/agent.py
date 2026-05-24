"""Core RAG agent — orchestrates: understand → retrieve → respond with citations.

Pipeline:
1. UNDERSTAND (GPT-4o-mini): detect intent + language, rewrite query for retrieval.
2. ROUTE (deterministic): greetings / off-topic / human handoff skip retrieval.
3. RETRIEVE (Weaviate hybrid search): top-k chunks from the document corpus.
4. RESPOND (GPT-4o): grounded answer with `[#N]` citations to chunk indices.

Every step is logged via `audit_steps` for the admin dashboard.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import openai

from backend.ai.schemas import (
    Citation,
    ConversationState,
    GenerateResult,
    UnderstandResult,
)
from backend.ai.understand import understand, update_state
from backend.core.config import settings
from backend.search.weaviate_client import (
    SearchResult,
    format_results_for_prompt,
    search_chunks,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "system.txt").read_text(encoding="utf-8")


def _get_system_prompt() -> str:
    """Resolve dynamic identity fields into the system prompt."""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        assistant_name=settings.assistant_name,
        organization=settings.organization,
    )


_GENERATE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "generate_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reply": {"type": "string"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
                "cited_chunk_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["reply", "confidence", "reasoning", "cited_chunk_ids"],
            "additionalProperties": False,
        },
    },
}

_NO_SEARCH_INTENTS = {"greeting", "off_topic", "human_request"}
_ESCALATION_INTENTS = {"human_request"}


@dataclass
class AgentResponse:
    reply: str
    language: str
    confidence: float
    search_results: list[SearchResult]
    citations: list[Citation]
    state: ConversationState
    understand_result: UnderstandResult
    reasoning: str
    duration_ms: int
    needs_escalation: bool
    audit_steps: list[dict] = field(default_factory=list)


async def chat(
    user_message: str,
    state: ConversationState,
    recent_messages: list[dict[str, str]],
    channel: str = "web",
) -> AgentResponse:
    """Run the full RAG pipeline for one user turn."""
    t0 = time.time()
    audit_steps: list[dict] = []

    # ── STEP 1: UNDERSTAND ──
    understood, understand_ms = await understand(user_message, state, recent_messages)

    # Preserve established conversation language after the first turn
    if recent_messages:
        understood.language = state.language or understood.language

    state = update_state(state, understood)

    audit_steps.append({
        "step": "understand",
        "model": settings.understand_model,
        "duration_ms": understand_ms,
        "result": understood.model_dump(),
    })

    # ── STEP 2: ROUTE ──
    search_results: list[SearchResult] = []
    search_query = ""

    if understood.intent in _NO_SEARCH_INTENTS:
        route_decision = "no_search"
    else:
        route_decision = "search"
        search_query = understood.search_query or user_message

    # ── STEP 3: RETRIEVE ──
    if route_decision == "search" and search_query.strip():
        search_results = await search_chunks(
            query=search_query,
            limit=settings.top_k_chunks,
        )

        audit_steps.append({
            "step": "search",
            "query": search_query,
            "results_count": len(search_results),
            "top_scores": [round(r.score, 3) for r in search_results[:3]],
            "reranked": False,
        })

    # ── STEP 4: RESPOND ──
    context_block = format_results_for_prompt(search_results)
    gen_result, gen_ms = await _generate_response(
        user_message=user_message,
        state=state,
        understood=understood,
        context_block=context_block,
        recent_messages=recent_messages,
        route_decision=route_decision,
    )

    audit_steps.append({
        "step": "generate",
        "model": settings.generate_model,
        "duration_ms": gen_ms,
        "confidence": gen_result.confidence,
        "cited_chunk_ids": gen_result.cited_chunk_ids,
    })

    # ── Build citations from cited chunk IDs ──
    by_id = {r.chunk_id: r for r in search_results}
    citations: list[Citation] = []
    for cid in gen_result.cited_chunk_ids:
        r = by_id.get(cid)
        if not r:
            continue
        excerpt = r.content.strip()
        if len(excerpt) > 280:
            excerpt = excerpt[:280] + "..."
        citations.append(Citation(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_title=r.document_title,
            document_type=r.document_type,
            source_url=r.source_url,
            page_number=r.page_number or None,
            section=r.section,
            excerpt=excerpt,
        ))

    # Track chunks already shown across turns
    for c in citations:
        if c.chunk_id and c.chunk_id not in state.cited_chunk_ids:
            state.cited_chunk_ids.append(c.chunk_id)

    # ── Confidence adjustment ──
    final_confidence = gen_result.confidence
    if route_decision == "search" and not search_results:
        final_confidence = min(final_confidence, 0.3)
    elif route_decision == "search" and search_results:
        top_score = max(r.score for r in search_results)
        if top_score < 0.4:
            final_confidence = min(final_confidence, 0.5)

    needs_escalation = (
        final_confidence < settings.escalation_confidence_floor
        or understood.intent in _ESCALATION_INTENTS
    )
    if needs_escalation:
        state.needs_escalation = True
        if not state.escalation_reason:
            state.escalation_reason = (
                understood.intent if understood.intent in _ESCALATION_INTENTS else "low_confidence"
            )
            state.escalation_status = "pending"

    total_ms = int((time.time() - t0) * 1000)

    return AgentResponse(
        reply=gen_result.reply,
        language=state.language,
        confidence=final_confidence,
        search_results=search_results,
        citations=citations,
        state=state,
        understand_result=understood,
        reasoning=gen_result.reasoning,
        duration_ms=total_ms,
        needs_escalation=needs_escalation,
        audit_steps=audit_steps,
    )


async def _generate_response(
    user_message: str,
    state: ConversationState,
    understood: UnderstandResult,
    *,
    context_block: str,
    recent_messages: list[dict[str, str]],
    route_decision: str = "search",
) -> tuple[GenerateResult, int]:
    """Generate the final grounded answer with GPT-4o."""
    t0 = time.time()

    messages = [{"role": "system", "content": _get_system_prompt()}]
    for msg in recent_messages[-settings.history_window_size:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    augmented = (
        f"User message: {user_message}\n\n"
        f"---\n"
        f"Intent: {understood.intent}\n"
        f"Route: {route_decision}\n"
        f"Language: {state.language}\n"
        f"---\n\n"
        f"Retrieved context:\n{context_block}\n\n"
        f"---\n\n"
        f"Reply rules:\n"
        f"- Answer in {'French' if state.language == 'fr' else 'English'}.\n"
        f"- Cite every factual claim with [#N] referencing the bracketed chunk index above.\n"
        f"- If the context does not contain the answer, say so honestly and do NOT invent facts.\n"
        f'- Return JSON: {{"reply": "...", "confidence": 0.0-1.0, "reasoning": "...", "cited_chunk_ids": ["..."]}}.\n'
        f"- Populate `cited_chunk_ids` with the EXACT 'Chunk ID' values of chunks you actually used."
    )
    messages.append({"role": "user", "content": augmented})

    oai = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await oai.chat.completions.create(
            model=settings.generate_model,
            messages=messages,
            response_format=_GENERATE_SCHEMA,
            temperature=0.3,
            max_tokens=settings.answer_max_tokens,
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        result = GenerateResult(**parsed)
    except Exception as e:
        logger.error("Generation failed: %s", e)
        fallback_msg = (
            "Désolé, une erreur technique est survenue. Merci de réessayer dans un instant."
            if state.language == "fr"
            else "Sorry, a technical error occurred. Please try again shortly."
        )
        result = GenerateResult(
            reply=fallback_msg,
            confidence=0.1,
            reasoning=f"Generation error: {e}",
            cited_chunk_ids=[],
        )

    duration_ms = int((time.time() - t0) * 1000)
    return result, duration_ms
