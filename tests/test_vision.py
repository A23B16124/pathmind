import numpy as np
import pytest
import torch
from unittest.mock import MagicMock, patch


def test_aggregate_slide_mean_pool():
    from src.vision.uni2 import aggregate_slide
    embs = np.random.randn(100, 1280).astype(np.float32)
    slide_vec = aggregate_slide(embs, device="cpu")
    assert slide_vec.shape == (1280,)
    np.testing.assert_allclose(slide_vec, embs.mean(axis=0), atol=1e-5)


def test_encode_tiles_output_shape():
    from src.vision.virchow2 import encode_tiles
    mock_model = MagicMock(return_value=torch.zeros(2, 257, 1280))
    mock_transforms = MagicMock(side_effect=lambda img: torch.zeros(3, 224, 224))
    tiles = [np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8) for _ in range(2)]
    with patch("src.vision.virchow2.torch.stack", return_value=torch.zeros(2, 3, 224, 224)):
        result = encode_tiles(tiles, mock_model, mock_transforms, device="cpu", batch_size=2)
    assert isinstance(result, np.ndarray)
