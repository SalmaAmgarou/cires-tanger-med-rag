"""Page-aware chunking with overlap.

Strategy: accumulate paragraphs within a single page until target_chunk_chars is
reached, then emit a chunk; the tail of each chunk is carried as overlap into
the next so concepts that span a boundary still match.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.documents.parser import PageText


@dataclass
class TextChunk:
    page_number: int
    chunk_index: int
    content: str
    section: str = ""


def chunk_pages(
    pages: list[PageText],
    target_chunk_chars: int = 1400,
    overlap_chars: int = 200,
) -> list[TextChunk]:
    """Chunk a sequence of pages into roughly target_chunk_chars pieces."""
    chunks: list[TextChunk] = []
    global_idx = 0

    for page in pages:
        paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in page.text.split("\n") if p.strip()]

        buf = ""
        for para in paragraphs:
            candidate = (buf + "\n\n" + para).strip() if buf else para
            if len(candidate) < target_chunk_chars:
                buf = candidate
                continue

            if buf:
                chunks.append(TextChunk(
                    page_number=page.page_number,
                    chunk_index=global_idx,
                    content=buf,
                ))
                global_idx += 1
                tail = buf[-overlap_chars:] if overlap_chars > 0 else ""
                buf = (tail + "\n\n" + para).strip() if tail else para
            else:
                buf = para

        if buf:
            chunks.append(TextChunk(
                page_number=page.page_number,
                chunk_index=global_idx,
                content=buf,
            ))
            global_idx += 1

    return chunks
