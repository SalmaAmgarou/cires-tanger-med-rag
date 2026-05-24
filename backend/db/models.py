import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(default=None)
    language: Mapped[str] = mapped_column(default="fr")
    status: Mapped[str] = mapped_column(default="active")  # active, closed, escalated
    state: Mapped[dict | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str]  # user, assistant, system
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[dict | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str | None] = mapped_column(Text, default=None, unique=True)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    document_type: Mapped[str | None] = mapped_column(default=None, index=True)  # annual_report, press_release, brochure, csr, financial
    organization: Mapped[str | None] = mapped_column(default=None, index=True)  # tanger_med, cires_technologies
    language: Mapped[str | None] = mapped_column(default=None, index=True)
    publish_date: Mapped[str | None] = mapped_column(default=None)
    total_pages: Mapped[int | None] = mapped_column(Integer, default=None)
    file_path: Mapped[str | None] = mapped_column(default=None)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    section: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("idx_chunk_document_page", "document_id", "page_number"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"), default=None)
    action: Mapped[str]  # e.g. "search", "llm_call", "rewrite", "escalation"
    input_data: Mapped[str | None] = mapped_column(Text, default=None)
    output_data: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    model_used: Mapped[str | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
