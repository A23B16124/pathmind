"""Semantic search over the PathMind literature index.

Uses the existing Jarvis sentence-transformers cache + Qdrant. No new model
download. Falls back to an empty result list on any error so the agent
pipeline never crashes because of RAG infra.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("PATHMIND_COLLECTION", "pathmind_literature")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def search_literature(
    query: str,
    limit: int = 6,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return up to `limit` literature chunks ranked by cosine similarity.

    Each result is a dict with: chunk_id, source, title, text, score, metadata.
    Returns [] on any error (collection missing, Qdrant down, etc.).
    """
    try:
        emb = _model().encode([query], convert_to_numpy=True)[0].tolist()
        client = _client()
        if COLLECTION not in [c.name for c in client.get_collections().collections]:
            return []
        flt = None
        if source_filter:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            flt = Filter(must=[FieldCondition(key="source", match=MatchValue(value=source_filter))])
        resp = client.query_points(
            collection_name=COLLECTION,
            query=emb,
            limit=limit,
            query_filter=flt,
            with_payload=True,
        )
        hits = resp.points if hasattr(resp, "points") else resp
        return [
            {
                "chunk_id": h.payload.get("chunk_id"),
                "source": h.payload.get("source"),
                "pmid": h.payload.get("pmid"),
                "title": h.payload.get("title"),
                "text": h.payload.get("text"),
                "score": h.score,
                "metadata": {k: v for k, v in h.payload.items() if k not in {"chunk_id", "source", "pmid", "title", "text"}},
            }
            for h in hits
        ]
    except Exception as e:
        print(f"[rag] search_literature error: {e}")
        return []


def format_for_prompt(hits: list[dict[str, Any]], max_chars_each: int = 600) -> str:
    """Format hits as a compact context block to inject into the agent prompt."""
    if not hits:
        return "[no literature retrieved]"
    blocks = []
    for i, h in enumerate(hits, 1):
        src = h.get("source", "?")
        ref = f"PMID {h['pmid']}" if h.get("pmid") else h.get("metadata", {}).get("case_id", "")
        title = h.get("title", "")
        snippet = (h.get("text") or "")[:max_chars_each]
        score = h.get("score", 0.0)
        blocks.append(f"[{i}] ({src}, {ref}, score={score:.2f}) {title}\n{snippet}")
    return "\n\n".join(blocks)
