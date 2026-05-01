import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from src.observability.stream import emit, get_queue


@pytest.mark.asyncio
async def test_embed_query_returns_vector():
    from src.rag.literature import embed_query
    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros(768, dtype=np.float32)
    with patch("src.rag.literature.SentenceTransformer", return_value=mock_model):
        # clear cached model from prior test
        import src.rag.literature as lit_mod
        if hasattr(lit_mod.embed_query, "_model"):
            delattr(lit_mod.embed_query, "_model")
        vec = await embed_query("breast cancer grade III")
    assert isinstance(vec, np.ndarray)
    assert vec.shape[0] > 0


@pytest.mark.asyncio
async def test_retrieve_literature_mock():
    from src.rag.literature import retrieve_literature
    mock_hit = MagicMock()
    mock_hit.payload = {"pmid": "12345", "title": "Test", "abstract": "...", "year": 2022}
    mock_hit.score = 0.95
    with patch("src.rag.literature.client") as mock_client:
        mock_client.search = AsyncMock(return_value=[mock_hit])
        vec = np.random.randn(768).astype(np.float32)
        results = await retrieve_literature(vec, top_k=1)
    assert results[0]["pmid"] == "12345"


@pytest.mark.asyncio
async def test_sse_queue_emit_receive():
    await emit("case_test_unique_id", "histopath_done", {"slide_id": "slide_01"})
    q = get_queue("case_test_unique_id")
    msg = q.get_nowait()
    assert msg["event"] == "histopath_done"
    assert msg["data"]["slide_id"] == "slide_01"
