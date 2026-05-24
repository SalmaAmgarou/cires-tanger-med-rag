"""Ingest a corpus of PDFs into PostgreSQL + Weaviate.

Usage:
    python -m backend.documents.ingest [--manifest corpus/manifest.json] [--keep-collection]

Manifest schema (corpus/manifest.json):
    {
      "documents": [
        {
          "source_url": "https://...pdf",
          "title": "Tanger Med Port Activity Report 2024",
          "document_type": "annual_report",
          "organization": "tanger_med",
          "language": "fr",
          "publish_date": "2025-01-22",
          "local_path": "tanger_med_port_activity_2024.pdf"
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import openai
import psycopg2
import psycopg2.extras

from backend.documents.chunker import chunk_pages
from backend.documents.parser import detect_language, extract_pages

PG_DSN = os.environ.get(
    "DATABASE_URL_SYNC",
    "host=localhost port=5432 dbname=rag user=rag password=rag_dev_password",
)
WEAVIATE_URL = os.environ.get("WEAVIATE_URL_HOST", "http://localhost:8080")
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 64

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "corpus"
PDF_DIR = CORPUS_DIR / "pdfs"


def create_pg_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_url TEXT UNIQUE,
                title TEXT,
                document_type TEXT,
                organization TEXT,
                language TEXT,
                publish_date TEXT,
                total_pages INTEGER,
                file_path TEXT,
                ingested_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_documents_organization ON documents(organization);
            CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
            CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language);

            CREATE TABLE IF NOT EXISTS chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                page_number INTEGER,
                section TEXT,
                content TEXT NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_document_page ON chunks(document_id, page_number);
            """
        )
    conn.commit()
    print("PostgreSQL: documents + chunks tables ready")


def create_weaviate_collection(client: httpx.Client) -> None:
    # Drop existing if any
    client.delete(f"{WEAVIATE_URL}/v1/schema/Chunks")

    schema = {
        "class": "Chunks",
        "vectorizer": "none",
        "properties": [
            {"name": "chunk_id", "dataType": ["text"], "tokenization": "field"},
            {"name": "document_id", "dataType": ["text"], "tokenization": "field"},
            {"name": "document_title", "dataType": ["text"], "tokenization": "word"},
            {"name": "document_type", "dataType": ["text"], "tokenization": "field"},
            {"name": "organization", "dataType": ["text"], "tokenization": "field"},
            {"name": "language", "dataType": ["text"], "tokenization": "field"},
            {"name": "source_url", "dataType": ["text"], "tokenization": "field"},
            {"name": "page_number", "dataType": ["int"]},
            {"name": "section", "dataType": ["text"], "tokenization": "word"},
            {"name": "content", "dataType": ["text"], "tokenization": "word"},
        ],
        "invertedIndexConfig": {"bm25": {"b": 0.75, "k1": 1.2}},
        "vectorIndexConfig": {"distance": "cosine"},
    }

    resp = client.post(f"{WEAVIATE_URL}/v1/schema", json=schema)
    if resp.status_code not in (200, 201):
        print(f"Weaviate schema error: {resp.status_code} {resp.text}")
        sys.exit(1)
    print("Weaviate: Chunks collection created")


def download_pdf(url: str, dest: Path, timeout: float = 60) -> bool:
    if dest.exists() and dest.stat().st_size > 1024:
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # verify=False because the slim base image ships with an older CA bundle
        # that doesn't yet trust some of Tanger Med's certificate chains. The
        # downloaded PDFs are public, so the integrity risk is low for a demo.
        with httpx.Client(timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (RAG-Ingest)"},
            )
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"  Download failed for {url}: {e}")
        return False


def upsert_document(conn, doc: dict) -> str:
    payload = {**doc, "id": str(uuid.uuid4())}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents
                (id, source_url, title, document_type, organization, language, publish_date, total_pages, file_path)
            VALUES
                (%(id)s, %(source_url)s, %(title)s, %(document_type)s, %(organization)s,
                 %(language)s, %(publish_date)s, %(total_pages)s, %(file_path)s)
            ON CONFLICT (source_url) DO UPDATE SET
                title = EXCLUDED.title,
                document_type = EXCLUDED.document_type,
                organization = EXCLUDED.organization,
                language = EXCLUDED.language,
                publish_date = EXCLUDED.publish_date,
                total_pages = EXCLUDED.total_pages,
                file_path = EXCLUDED.file_path,
                ingested_at = now()
            RETURNING id
            """,
            payload,
        )
        row = cur.fetchone()
        doc_id = str(row[0])
        cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
    conn.commit()
    return doc_id


def insert_chunks_pg(conn, chunks_data: list[dict]) -> None:
    cols = ["id", "document_id", "chunk_index", "page_number", "section", "content", "token_count"]
    query = f"INSERT INTO chunks ({', '.join(cols)}) VALUES ({', '.join([f'%({c})s' for c in cols])})"
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, query, chunks_data, page_size=100)
    conn.commit()


def get_embeddings(oai: openai.OpenAI, texts: list[str]) -> list[list[float]]:
    resp = oai.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def insert_chunks_weaviate(
    client: httpx.Client,
    chunks_data: list[dict],
    document_meta: dict,
    vectors: list[list[float]],
) -> int:
    objects = []
    for chunk, vec in zip(chunks_data, vectors):
        objects.append(
            {
                "class": "Chunks",
                "properties": {
                    "chunk_id": chunk["id"],
                    "document_id": chunk["document_id"],
                    "document_title": document_meta.get("title") or "",
                    "document_type": document_meta.get("document_type") or "",
                    "organization": document_meta.get("organization") or "",
                    "language": document_meta.get("language") or "",
                    "source_url": document_meta.get("source_url") or "",
                    "page_number": int(chunk.get("page_number") or 0),
                    "section": chunk.get("section") or "",
                    "content": chunk["content"],
                },
                "vector": vec,
            }
        )

    resp = client.post(
        f"{WEAVIATE_URL}/v1/batch/objects",
        json={"objects": objects},
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"  Weaviate batch error: {resp.status_code} {resp.text[:300]}")
        return 0

    results = resp.json()
    errors = [r for r in results if r.get("result", {}).get("errors")]
    if errors:
        print(f"  Weaviate: {len(errors)} object errors in batch")
        for e in errors[:2]:
            print(f"    {e['result']['errors']}")
    return len(objects) - len(errors)


def ingest_pdf(conn, weaviate_client, oai, pdf_path: Path, doc_meta: dict) -> None:
    print(f"  Parsing {pdf_path.name} ...")
    t0 = time.time()
    pages, pdf_meta = extract_pages(pdf_path)
    if not pages:
        print("  Skipping (no text extracted — likely scanned PDF without OCR)")
        return

    if not doc_meta.get("language"):
        sample = " ".join(p.text[:500] for p in pages[:3])
        doc_meta["language"] = detect_language(sample)

    doc_meta["total_pages"] = pdf_meta.get("total_pages", len(pages))
    doc_meta["file_path"] = str(pdf_path)

    doc_id = upsert_document(conn, doc_meta)

    chunks = chunk_pages(pages)
    if not chunks:
        print("  No chunks produced")
        return
    print(f"  Chunked into {len(chunks)} pieces")

    chunks_data = []
    for c in chunks:
        chunks_data.append(
            {
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section": c.section,
                "content": c.content,
                "token_count": max(1, len(c.content) // 4),
            }
        )
    insert_chunks_pg(conn, chunks_data)

    weaviate_meta = {**doc_meta, "document_id": doc_id}
    total = 0
    for i in range(0, len(chunks_data), BATCH_SIZE):
        batch = chunks_data[i : i + BATCH_SIZE]
        texts = [b["content"] for b in batch]
        try:
            vectors = get_embeddings(oai, texts)
        except Exception as e:
            print(f"  Embedding error at batch {i}: {e}")
            continue
        n = insert_chunks_weaviate(weaviate_client, batch, weaviate_meta, vectors)
        total += n
    elapsed = time.time() - t0
    print(f"  Stored {total}/{len(chunks_data)} chunks in {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(CORPUS_DIR / "manifest.json"))
    parser.add_argument("--keep-collection", action="store_true",
                        help="Do not drop and re-create the Weaviate Chunks collection")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    docs_to_ingest = manifest.get("documents", [])
    if not docs_to_ingest:
        print("Manifest contains no documents")
        sys.exit(0)
    print(f"Manifest: {len(docs_to_ingest)} documents to ingest\n")

    conn = psycopg2.connect(PG_DSN)
    create_pg_tables(conn)

    weaviate_client = httpx.Client(timeout=60)
    if not args.keep_collection:
        create_weaviate_collection(weaviate_client)

    oai = openai.OpenAI()

    for i, doc in enumerate(docs_to_ingest, 1):
        print(f"[{i}/{len(docs_to_ingest)}] {doc.get('title') or doc.get('source_url')}")
        source_url = doc.get("source_url", "")
        local_path = doc.get("local_path") or _filename_from_url(source_url)
        pdf_path = PDF_DIR / local_path

        if source_url and not pdf_path.exists():
            print(f"  Downloading {source_url}")
            ok = download_pdf(source_url, pdf_path)
            if not ok:
                continue

        if not pdf_path.exists():
            print(f"  PDF missing: {pdf_path}")
            continue

        ingest_pdf(conn, weaviate_client, oai, pdf_path, doc)
        print()

    weaviate_client.close()
    conn.close()
    print("Ingestion complete.")


def _filename_from_url(url: str) -> str:
    name = url.rsplit("/", 1)[-1] if url else ""
    return name or "document.pdf"


if __name__ == "__main__":
    main()
