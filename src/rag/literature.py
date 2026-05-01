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
    hits = await client.search(
        collection_name=COLLECTION,
        query_vector=query_embedding.tolist(),
        limit=top_k,
        with_payload=True,
    )
    return [{
        "pmid": h.payload["pmid"],
        "title": h.payload["title"],
        "abstract": h.payload["abstract"],
        "year": h.payload.get("year"),
        "score": round(h.score, 4),
    } for h in hits]
