"""Weaviate hybrid (BM25 + vector) search over document chunks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
import openai

from backend.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    document_title: str
    document_type: str
    source_url: str
    organization: str
    language: str
    page_number: int
    section: str
    content: str
    score: float


async def search_chunks(
    query: str,
    limit: int = 6,
    alpha: float | None = None,
    organization_filter: str = "",
    language_filter: str = "",
) -> list[SearchResult]:
    """Hybrid (BM25 + vector) search over the Chunks collection.

    Args:
        query: Natural-language retrieval query (FR or EN).
        limit: Max chunks to return.
        alpha: 0 = pure BM25, 1 = pure vector. Defaults to settings.weaviate_alpha (0.65 = semantic-leaning).
        organization_filter: Restrict to a single org (e.g. "tanger_med", "cires_technologies").
        language_filter: Restrict to a single language ("fr", "en").
    """
    if alpha is None:
        alpha = settings.weaviate_alpha

    if not query.strip():
        return []

    oai = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    vector = None
    try:
        emb_resp = await oai.embeddings.create(model=EMBEDDING_MODEL, input=query)
        vector = emb_resp.data[0].embedding
    except Exception as e:
        logger.warning("Embedding failed, falling back to BM25-only: %s", e)
        alpha = 0

    where_clause = _build_where(organization_filter, language_filter)

    escaped_query = query.replace('"', '\\"').replace("\n", " ")
    vector_line = f"vector: {json.dumps(vector)}" if vector else ""
    graphql_query = """
    {
        Get {
            Chunks(
                hybrid: {
                    query: "%s"
                    %s
                    alpha: %s
                }
                %s
                limit: %d
            ) {
                chunk_id
                document_id
                document_title
                document_type
                source_url
                organization
                language
                page_number
                section
                content
                _additional { score }
            }
        }
    }
    """ % (escaped_query, vector_line, alpha, where_clause, limit)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error("Weaviate search failed: %s", e)
        return []

    data = resp.json()
    if data.get("errors"):
        logger.error("Weaviate GQL errors: %s", data["errors"])
        if where_clause:
            logger.info("Retrying search without filters")
            return await search_chunks(query, limit, alpha)
        return []

    raw_results = data.get("data", {}).get("Get", {}).get("Chunks", []) or []

    results: list[SearchResult] = []
    for r in raw_results:
        score = float(r.get("_additional", {}).get("score", 0))
        if score < settings.min_search_relevance:
            continue
        results.append(
            SearchResult(
                chunk_id=r.get("chunk_id", "") or "",
                document_id=r.get("document_id", "") or "",
                document_title=r.get("document_title", "") or "",
                document_type=r.get("document_type", "") or "",
                source_url=r.get("source_url", "") or "",
                organization=r.get("organization", "") or "",
                language=r.get("language", "") or "",
                page_number=int(r.get("page_number") or 0),
                section=r.get("section", "") or "",
                content=r.get("content", "") or "",
                score=score,
            )
        )

    return results


def _build_where(organization: str, language: str) -> str:
    conditions = []
    if organization:
        conditions.append(
            '{path: ["organization"], operator: Equal, valueText: "%s"}'
            % organization.replace('"', '\\"')
        )
    if language:
        conditions.append(
            '{path: ["language"], operator: Equal, valueText: "%s"}'
            % language.replace('"', '\\"')
        )
    if not conditions:
        return ""
    if len(conditions) == 1:
        return f"where: {conditions[0]}"
    return "where: {operator: And, operands: [%s]}" % ", ".join(conditions)


def format_results_for_prompt(results: list[SearchResult]) -> str:
    """Format chunks into a numbered context block for the LLM prompt."""
    if not results:
        return "No relevant content found in the document corpus."

    lines = []
    for i, r in enumerate(results, 1):
        page_str = f", p.{r.page_number}" if r.page_number else ""
        section_str = f" — {r.section}" if r.section else ""
        content = r.content.strip()
        if len(content) > 1200:
            content = content[:1200] + "..."
        lines.append(
            f"[{i}] {r.document_title}{page_str}{section_str}\n"
            f"    Org: {r.organization} | Type: {r.document_type} | Lang: {r.language}\n"
            f"    Source URL: {r.source_url or '(local)'}\n"
            f"    Chunk ID: {r.chunk_id}\n"
            f"    Content:\n{content}\n"
            f"    Relevance: {r.score:.2f}"
        )
    return "\n\n".join(lines)
