import numpy as np
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.wsi.loader import iter_tissue_tiles
from src.wsi.cache import TileCache
from src.wsi.downloader import search_tcga_slides

MINI_SLIDE = "tests/fixtures/mini_slide.tiff"

def test_iter_tissue_tiles_returns_arrays():
    tiles = list(iter_tissue_tiles(MINI_SLIDE, tile_size=256, level=0, otsu_threshold=100))
    assert len(tiles) > 0
    row, col, arr = tiles[0]
    assert arr.shape == (256, 256, 3)
    assert arr.dtype == np.uint8

def test_tissue_filter_removes_background():
    all_tiles = list(iter_tissue_tiles(MINI_SLIDE, tile_size=256, level=0, otsu_threshold=10))
    strict_tiles = list(iter_tissue_tiles(MINI_SLIDE, tile_size=256, level=0, otsu_threshold=200))
    assert len(strict_tiles) <= len(all_tiles)

def test_tile_cache_roundtrip(tmp_path):
    cache = TileCache(cache_dir=str(tmp_path))
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    key = cache.key(MINI_SLIDE, tile_size=256, level=0)
    cache.save(key, [arr])
    loaded = cache.load(key)
    assert loaded is not None
    np.testing.assert_array_equal(loaded[0], arr)

def test_tile_cache_miss_returns_none(tmp_path):
    cache = TileCache(cache_dir=str(tmp_path))
    assert cache.load("nonexistent_key") is None

@pytest.mark.asyncio
async def test_search_tcga_slides_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"hits": [{"file_id": "abc-123", "file_name": "slide.svs", "file_size": 500000000}]},
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        results = await search_tcga_slides(project="TCGA-BRCA", histology="Infiltrating Ductal Carcinoma", limit=5)
    assert isinstance(results, list)
    assert results[0]["file_id"] == "abc-123"
