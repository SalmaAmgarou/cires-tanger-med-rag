"""Pydantic schemas for the RAG AI pipeline — conversation state, query understanding, generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """A single source citation referenced in an answer."""
    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(default="")
    document_id: str = Field(default="")
    document_title: str = Field(default="")
    document_type: str = Field(default="")
    source_url: str = Field(default="")
    page_number: int | None = Field(default=None)
    section: str = Field(default="")
    excerpt: str = Field(default="")


class ConversationState(BaseModel):
    """State accumulated across conversation turns for a document Q&A flow."""
    model_config = ConfigDict(extra="ignore")

    language: str = Field(default="fr", description="Conversation language: 'fr' or 'en'")
    cited_chunk_ids: list[str] = Field(default_factory=list, description="Chunks already cited in this conversation")
    pending_question: str = Field(default="", description="A clarification we are waiting on, if any")
    needs_escalation: bool = Field(default=False)
    escalation_reason: str = Field(default="")
    escalation_status: str = Field(default="")


class UnderstandResult(BaseModel):
    """Output of the understand step (GPT-4o-mini)."""

    intent: str = Field(
        description="One of: greeting, question, follow_up, clarification, off_topic, human_request"
    )
    language: str = Field(description="'fr' or 'en'")
    search_query: str = Field(
        default="",
        description="Standalone retrieval query combining the current question with prior context. Empty if no search needed.",
    )
    confidence: float = Field(default=0.5, description="0.0-1.0 confidence in the interpretation")
    reasoning: str = Field(default="", description="Brief audit note in English")


class GenerateResult(BaseModel):
    """Output of the response generation step (GPT-4o)."""

    reply: str = Field(description="Final user-facing response in the user's language")
    confidence: float = Field(description="0.0-1.0 confidence in the response quality")
    reasoning: str = Field(description="Brief audit note in English")
    cited_chunk_ids: list[str] = Field(default_factory=list, description="IDs of chunks actually relied on in the reply")
