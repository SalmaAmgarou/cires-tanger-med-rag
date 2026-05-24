"""Chat API endpoint — handles user questions against the document corpus."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.agent import AgentResponse, chat
from backend.ai.schemas import ConversationState
from backend.core.config import settings
from backend.db.base import get_db
from backend.db.models import AuditLog, Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(max_length=2000)
    conversation_id: str | None = None
    channel: str = Field(default="web")


class DebugCitation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    document_type: str
    source_url: str
    page_number: int | None = None
    section: str
    excerpt: str


class DebugChunkResult(BaseModel):
    chunk_id: str
    document_title: str
    document_type: str
    organization: str
    language: str
    page_number: int
    section: str
    score: float
    source_url: str


class DebugUnderstand(BaseModel):
    intent: str
    language: str
    search_query: str
    confidence: float
    reasoning: str


class DebugPipelineStep(BaseModel):
    step: str
    model: str | None = None
    duration_ms: int | None = None
    query: str | None = None
    results_count: int | None = None
    top_scores: list[float] | None = None
    reranked: bool | None = None
    confidence: float | None = None
    cited_chunk_ids: list[str] | None = None
    result: dict | None = None


class DebugTrace(BaseModel):
    understand: DebugUnderstand
    search_results: list[DebugChunkResult]
    conversation_state: dict
    pipeline_steps: list[DebugPipelineStep]
    reasoning: str


class ChatResponseModel(BaseModel):
    conversation_id: str
    reply: str
    language: str
    confidence: float
    needs_escalation: bool
    intent: str
    chunks_found: int
    duration_ms: int
    citations: list[DebugCitation]
    debug: DebugTrace


@router.post("", response_model=ChatResponseModel)
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChatResponseModel:
    """Process a user message and return a grounded RAG response with citations."""

    conversation, state, history = await _get_or_create_conversation(db, req.conversation_id)

    # Persist user message immediately for audit trail
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()

    # Run the RAG pipeline
    result: AgentResponse = await chat(
        req.message,
        state,
        history,
        channel=req.channel,
    )

    citations_payload = [c.model_dump() for c in result.citations]

    # Persist assistant message with attached citations
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.reply,
        citations={"items": citations_payload} if citations_payload else None,
    )
    db.add(assistant_msg)

    # Update conversation state
    conversation.state = result.state.model_dump()
    conversation.language = result.language
    if result.needs_escalation:
        conversation.status = "escalated"

    chunk_summary = [
        {
            "chunk_id": r.chunk_id,
            "document_title": r.document_title,
            "document_type": r.document_type,
            "organization": r.organization,
            "language": r.language,
            "page_number": r.page_number,
            "score": r.score,
            "source_url": r.source_url,
        }
        for r in result.search_results
    ]

    audit = AuditLog(
        conversation_id=conversation.id,
        action="chat_response",
        input_data=json.dumps(
            {
                "message": req.message,
                "intent": result.understand_result.intent,
                "language": result.language,
                "search_query": result.understand_result.search_query,
            },
            ensure_ascii=False,
        ),
        output_data=json.dumps(
            {
                "reply": result.reply,
                "citations": citations_payload,
                "search_results": chunk_summary,
                "pipeline_steps": result.audit_steps,
            },
            ensure_ascii=False,
        ),
        confidence=result.confidence,
        reasoning=result.reasoning,
        model_used=f"{settings.understand_model} + {settings.generate_model}",
        duration_ms=result.duration_ms,
    )
    db.add(audit)

    await db.commit()

    debug_search = [
        DebugChunkResult(
            chunk_id=r.chunk_id,
            document_title=r.document_title,
            document_type=r.document_type,
            organization=r.organization,
            language=r.language,
            page_number=r.page_number,
            section=r.section,
            score=r.score,
            source_url=r.source_url,
        )
        for r in result.search_results
    ]

    debug_understand = DebugUnderstand(
        intent=result.understand_result.intent,
        language=result.understand_result.language,
        search_query=result.understand_result.search_query,
        confidence=result.understand_result.confidence,
        reasoning=result.understand_result.reasoning,
    )

    debug_steps = []
    for step in result.audit_steps:
        # PipelineStep accepts only known fields — drop unknowns
        keep = {k: v for k, v in step.items() if k in DebugPipelineStep.model_fields}
        debug_steps.append(DebugPipelineStep(**keep))

    debug = DebugTrace(
        understand=debug_understand,
        search_results=debug_search,
        conversation_state=result.state.model_dump(),
        pipeline_steps=debug_steps,
        reasoning=result.reasoning,
    )

    citations_models = [DebugCitation(**c) for c in citations_payload]

    return ChatResponseModel(
        conversation_id=str(conversation.id),
        reply=result.reply,
        language=result.language,
        confidence=result.confidence,
        needs_escalation=result.needs_escalation,
        intent=result.understand_result.intent,
        chunks_found=len(result.search_results),
        duration_ms=result.duration_ms,
        citations=citations_models,
        debug=debug,
    )


async def _get_or_create_conversation(
    db: AsyncSession,
    conversation_id: str | None,
) -> tuple[Conversation, ConversationState, list[dict[str, str]]]:
    """Load an existing conversation + state + history, or create a fresh one."""

    if conversation_id:
        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            conv_uuid = None

        if conv_uuid:
            stmt = select(Conversation).where(Conversation.id == conv_uuid)
            result = await db.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                state = ConversationState()
                if conversation.state:
                    try:
                        state = ConversationState.model_validate(conversation.state)
                    except Exception:
                        logger.warning("Corrupted state for conversation %s, resetting", conversation.id)

                msg_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(20)
                )
                msg_result = await db.execute(msg_stmt)
                messages = list(reversed(msg_result.scalars().all()))

                history = [{"role": m.role, "content": m.content} for m in messages]
                return conversation, state, history

    conversation = Conversation(status="active")
    db.add(conversation)
    await db.flush()
    return conversation, ConversationState(), []
