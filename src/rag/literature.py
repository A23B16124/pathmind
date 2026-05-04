import numpy as np
from qdrant_client import AsyncQdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = "http://localhost:6333"
COLLECTION = "pubmed_abstracts"

client = AsyncQdrantClient(url=QDRANT_URL)


async def embed_query(text: str) -> np.ndarray:
    if not hasattr(embed_query, "_model"):
        embed_query._model = SentenceTransformer("dmis-lab/biobert-base-cased-v1.2")
    return embed_query._model.encode(text, normalize_embeddings=True)


async def retrieve_literature(query_embedding: np.ndarray, top_k: int = 20) -> list[dict]:
    resp = await client.query_points(
        collection_name=COLLECTION,
        query=query_embedding.tolist(),
        limit=top_k,
        with_payload=True,
    )
    hits = resp.points if hasattr(resp, "points") else resp
    return [{
        "pmid": h.payload["pmid"],
        "title": h.payload["title"],
        "abstract": h.payload["abstract"],
        "year": h.payload.get("year"),
        "score": round(h.score, 4),
    } for h in hits]
