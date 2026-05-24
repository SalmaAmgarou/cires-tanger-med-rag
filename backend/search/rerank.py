"""Cohere-based reranking for document chunks.

Optional, opt-in via settings.rerank_enabled. Uses a multilingual rerank model
suitable for FR + EN content.
"""

from __future__ import annotations

import logging

from backend.core.config import settings
from backend.search.weaviate_client import SearchResult

logger = logging.getLogger(__name__)


def _build_rerank_doc(result: SearchResult) -> str:
    """Compact text representation of a chunk for the reranker."""
    parts = []
    if result.document_title:
        parts.append(f"Document: {result.document_title}")
    if result.section:
        parts.append(f"Section: {result.section}")
    if result.page_number:
        parts.append(f"Page: {result.page_number}")
    if result.content:
        snippet = result.content[:600]
        parts.append(snippet)
    return " | ".join(parts)


async def rerank_results(
    query: str,
    results: list[SearchResult],
    top_n: int | None = None,
) -> list[SearchResult]:
    """Rerank chunk results with Cohere; fall back to truncated input on failure."""
    if top_n is None:
        top_n = settings.rerank_top_n

    if len(results) <= top_n:
        return results

    try:
        import cohere

        co = cohere.AsyncClient(api_key=settings.cohere_api_key)
        docs = [_build_rerank_doc(r) for r in results]

        response = await co.rerank(
            model=settings.rerank_model,
            query=query,
            documents=docs,
            top_n=top_n,
        )

        reranked: list[SearchResult] = []
        for item in response.results:
            original = results[item.index]
            original.score = item.relevance_score
            reranked.append(original)

        logger.info(
            "Reranked %d→%d chunks, top score=%.3f",
            len(results),
            len(reranked),
            reranked[0].score if reranked else 0,
        )
        return reranked

    except Exception as exc:
        logger.warning("Reranker failed, falling back to raw Weaviate scores: %s", exc)
        return results[:top_n]
