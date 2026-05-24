"""Admin API — conversation browser, audit trail, escalation queue, corpus stats, live upload."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.base import get_db
from backend.db.models import AuditLog, Chunk, Conversation, Document, Message

router = APIRouter(prefix="/admin", tags=["admin"])

UPLOAD_DIR = Path("/app/corpus/pdfs/uploads")
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_convos = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0
    escalated = (await db.execute(
        select(func.count(Conversation.id)).where(Conversation.status == "escalated")
    )).scalar() or 0
    avg_conf = (await db.execute(
        select(func.avg(AuditLog.confidence)).where(
            AuditLog.confidence.isnot(None),
            AuditLog.confidence > 0.0,
        )
    )).scalar()
    total_messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0

    return {
        "total_conversations": total_convos,
        "total_messages": total_messages,
        "avg_confidence": round(avg_conf, 2) if avg_conf else None,
        "escalation_count": escalated,
        "escalation_rate": round(escalated / total_convos * 100, 1) if total_convos > 0 else 0,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
    }


@router.get("/documents")
async def list_documents(
    organization: str | None = None,
    document_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Document).order_by(Document.ingested_at.desc())
    if organization:
        query = query.where(Document.organization == organization)
    if document_type:
        query = query.where(Document.document_type == document_type)

    result = await db.execute(query)
    docs = result.scalars().all()

    chunk_counts: dict[str, int] = {}
    if docs:
        cnt_result = await db.execute(
            select(Chunk.document_id, func.count(Chunk.id))
            .where(Chunk.document_id.in_([d.id for d in docs]))
            .group_by(Chunk.document_id)
        )
        for doc_id, n in cnt_result.all():
            chunk_counts[str(doc_id)] = n

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "document_type": d.document_type,
            "organization": d.organization,
            "language": d.language,
            "publish_date": d.publish_date,
            "total_pages": d.total_pages,
            "source_url": d.source_url,
            "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None,
            "chunk_count": chunk_counts.get(str(d.id), 0),
        }
        for d in docs
    ]


@router.get("/conversations")
async def list_conversations(
    limit: int = 50,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = min(limit, 500)

    last_msg_sq = (
        select(Message.conversation_id, Message.content.label("last_content"))
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.created_at.desc())
        .subquery()
    )
    last_conf_sq = (
        select(AuditLog.conversation_id, AuditLog.confidence.label("last_confidence"))
        .distinct(AuditLog.conversation_id)
        .order_by(AuditLog.conversation_id, AuditLog.created_at.desc())
        .subquery()
    )

    query = (
        select(Conversation, last_msg_sq.c.last_content, last_conf_sq.c.last_confidence)
        .outerjoin(last_msg_sq, Conversation.id == last_msg_sq.c.conversation_id)
        .outerjoin(last_conf_sq, Conversation.id == last_conf_sq.c.conversation_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Conversation.status == status)

    result = await db.execute(query)
    rows = result.all()

    out = []
    for c, last_msg, confidence in rows:
        out.append({
            "id": str(c.id),
            "user_id": c.user_id,
            "language": c.language,
            "status": c.status,
            "confidence": confidence,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "last_message": (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else last_msg,
        })
    return out


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Full conversation view with per-turn audit trail and citations."""
    conv = (await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()
    if not conv:
        return {"error": "Not found"}

    msgs_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    msgs = msgs_result.scalars().all()

    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.conversation_id == conv.id)
        .order_by(AuditLog.created_at)
    )
    audits = list(audit_result.scalars().all())
    audit_idx = 0

    messages = []
    for m in msgs:
        msg_data = {
            "role": m.role,
            "content": m.content,
            "citations": (m.citations or {}).get("items", []) if m.citations else [],
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        if m.role == "assistant" and audit_idx < len(audits):
            a = audits[audit_idx]
            audit_idx += 1
            input_data = _safe_json(a.input_data)
            output_data = _safe_json(a.output_data)
            msg_data["audit"] = {
                "confidence": a.confidence,
                "reasoning": a.reasoning,
                "duration_ms": a.duration_ms,
                "model_used": a.model_used,
                "intent": input_data.get("intent"),
                "language": input_data.get("language"),
                "search_query": input_data.get("search_query"),
                "citations": output_data.get("citations", []),
                "search_results": output_data.get("search_results", []),
                "pipeline_steps": output_data.get("pipeline_steps", []),
            }
        messages.append(msg_data)

    state = conv.state if conv.state else {}

    return {
        "id": str(conv.id),
        "user_id": conv.user_id,
        "language": conv.language,
        "status": conv.status,
        "state": state,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "messages": messages,
    }


@router.get("/conversations/{conversation_id}/audit")
async def get_conversation_audit(conversation_id: str, db: AsyncSession = Depends(get_db)):
    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.conversation_id == conversation_id)
        .order_by(AuditLog.created_at)
    )
    audits = audit_result.scalars().all()
    return [
        {
            "id": str(a.id),
            "action": a.action,
            "confidence": a.confidence,
            "reasoning": a.reasoning,
            "model_used": a.model_used,
            "duration_ms": a.duration_ms,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "input": _safe_json(a.input_data),
            "output": _safe_json(a.output_data),
        }
        for a in audits
    ]


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(..., description="A PDF file to ingest into the corpus"),
    title: str | None = Form(None, description="Optional document title; defaults to filename"),
    document_type: str = Form("uploaded"),
    organization: str = Form("user_uploaded"),
    language: str | None = Form(None, description="'fr' or 'en'; auto-detected if omitted"),
    publish_date: str | None = Form(None),
):
    """Upload a single PDF and ingest it into the corpus on the fly.

    Returns the freshly created document id, page count and chunk count so the
    UI can show feedback. Runs the sync ingest pipeline in a worker thread to
    avoid blocking the asyncio event loop.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are supported")

    safe_name = _FILENAME_SAFE_RE.sub("_", file.filename)
    pdf_path = UPLOAD_DIR / safe_name
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB upload limit")

    pdf_path.write_bytes(contents)

    doc_meta = {
        "source_url": f"upload://{safe_name}",
        "title": title or file.filename,
        "document_type": document_type,
        "organization": organization,
        "language": language,
        "publish_date": publish_date,
    }

    started = time.time()

    def _run_ingest() -> dict:
        # Lazy imports to keep the request-handler cold path light
        import httpx
        import openai
        import psycopg2

        from backend.documents.ingest import (
            PG_DSN,
            WEAVIATE_URL,
            create_pg_tables,
            ingest_pdf,
        )

        conn = psycopg2.connect(PG_DSN)
        weaviate_client = httpx.Client(timeout=60)
        try:
            create_pg_tables(conn)
            oai = openai.OpenAI()
            ingest_pdf(conn, weaviate_client, oai, pdf_path, doc_meta)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, total_pages,
                           (SELECT COUNT(*) FROM chunks WHERE document_id = documents.id)
                    FROM documents WHERE source_url = %s
                    """,
                    (doc_meta["source_url"],),
                )
                row = cur.fetchone()
            return {
                "document_id": str(row[0]) if row else None,
                "total_pages": row[1] if row else 0,
                "chunk_count": row[2] if row else 0,
            }
        finally:
            weaviate_client.close()
            conn.close()

    try:
        result = await asyncio.to_thread(_run_ingest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}") from e

    return {
        "ok": True,
        "title": doc_meta["title"],
        "filename": safe_name,
        "language": doc_meta.get("language"),
        "duration_ms": int((time.time() - started) * 1000),
        **result,
    }


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document (cascades to its chunks) from PostgreSQL and Weaviate."""
    import uuid
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = (await db.execute(
        select(Document).where(Document.id == doc_uuid)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(doc)
    await db.commit()

    # Also delete the chunks from Weaviate by document_id
    def _purge_weaviate() -> int:
        import httpx
        from backend.core.config import settings as cfg
        with httpx.Client(timeout=30) as client:
            # Step 1: GraphQL to fetch matching chunk UUIDs (Weaviate's stable
            # batch-delete REST API has been unreliable across minor versions, so
            # we fetch IDs and delete one-by-one, which works everywhere).
            gql = (
                '{ Get { Chunks(where: {path: ["document_id"], operator: Equal, '
                'valueText: "%s"}, limit: 1000) { _additional { id } } } }'
            ) % document_id
            resp = client.post(
                f"{cfg.weaviate_url}/v1/graphql",
                json={"query": gql},
            )
            resp.raise_for_status()
            chunks = (
                resp.json().get("data", {}).get("Get", {}).get("Chunks", []) or []
            )
            deleted = 0
            for c in chunks:
                cid = (c.get("_additional") or {}).get("id")
                if not cid:
                    continue
                r = client.delete(f"{cfg.weaviate_url}/v1/objects/Chunks/{cid}")
                if r.status_code in (200, 204):
                    deleted += 1
            return deleted

    try:
        purged = await asyncio.to_thread(_purge_weaviate)
    except Exception as e:
        return {"ok": True, "document_id": document_id, "weaviate_purge_error": str(e)}

    return {"ok": True, "document_id": document_id, "chunks_purged_from_weaviate": purged}


@router.get("/escalations")
async def get_escalations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.status == "escalated")
        .order_by(Conversation.updated_at.desc())
        .limit(20)
    )
    convos = result.scalars().all()

    out = []
    for c in convos:
        audit = (await db.execute(
            select(AuditLog)
            .where(AuditLog.conversation_id == c.id)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        last_msg = (await db.execute(
            select(Message.content)
            .where(Message.conversation_id == c.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(1)
        )).scalar()

        input_data = _safe_json(audit.input_data) if audit else {}
        state = c.state or {}

        out.append({
            "conversation_id": str(c.id),
            "user_id": c.user_id,
            "language": c.language,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "last_user_message": last_msg,
            "confidence": audit.confidence if audit else None,
            "reasoning": audit.reasoning if audit else None,
            "intent": input_data.get("intent"),
            "search_query": input_data.get("search_query"),
            "escalation_reason": state.get("escalation_reason", ""),
            "escalation_status": state.get("escalation_status", "pending"),
        })
    return out


@router.patch("/escalations/{conversation_id}/status")
async def update_escalation_status(
    conversation_id: str,
    status: str = Query(..., description="pending, in_review, resolved, closed"),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return {"error": "Invalid conversation ID"}

    conv = (await db.execute(
        select(Conversation).where(Conversation.id == conv_uuid)
    )).scalar_one_or_none()
    if not conv:
        return {"error": "Conversation not found"}

    state = conv.state or {}
    state["escalation_status"] = status
    if status == "closed":
        conv.status = "closed"
    conv.state = state
    await db.commit()
    return {"ok": True, "conversation_id": conversation_id, "escalation_status": status}


def _safe_json(text: str | None) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _csv_response(buf: io.StringIO, filename: str) -> StreamingResponse:
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/summary")
async def export_summary(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Summary metrics report as CSV."""
    date_filter_conv = [
        Conversation.created_at >= from_date,
        Conversation.created_at < to_date + timedelta(days=1),
    ]
    date_filter_msg = [
        Message.created_at >= from_date,
        Message.created_at < to_date + timedelta(days=1),
    ]
    date_filter_audit = [
        AuditLog.created_at >= from_date,
        AuditLog.created_at < to_date + timedelta(days=1),
    ]

    total_convos = (await db.execute(
        select(func.count(Conversation.id)).where(*date_filter_conv)
    )).scalar() or 0
    total_messages = (await db.execute(
        select(func.count(Message.id)).where(*date_filter_msg)
    )).scalar() or 0
    escalation_count = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.status == "escalated", *date_filter_conv
        )
    )).scalar() or 0
    avg_confidence = (await db.execute(
        select(func.avg(AuditLog.confidence)).where(
            AuditLog.confidence.isnot(None), *date_filter_audit
        )
    )).scalar()
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Period", f"{from_date.isoformat()} to {to_date.isoformat()}"])
    writer.writerow(["Total Conversations", total_convos])
    writer.writerow(["Total Messages", total_messages])
    writer.writerow(["Escalation Count", escalation_count])
    writer.writerow(["Avg Confidence", round(avg_confidence, 2) if avg_confidence else "N/A"])
    writer.writerow(["Total Documents (corpus)", total_docs])
    writer.writerow(["Total Chunks (corpus)", total_chunks])

    filename = f"summary_{from_date.isoformat()}_{to_date.isoformat()}.csv"
    return _csv_response(buf, filename)
