import numpy as np
import cv2
from dataclasses import dataclass

@dataclass
class TileScore:
    row: int
    col: int
    score: float
    reason: str

def score_tile(embedding: np.ndarray, tile_rgb: np.ndarray) -> float:
    hsv = cv2.cvtColor(tile_rgb, cv2.COLOR_RGB2HSV)
    sat_score = float(hsv[:, :, 1].mean()) / 255.0
    var_score = float(tile_rgb.var()) / 65025.0
    emb_score = float(np.linalg.norm(embedding)) / 50.0
    return 0.4 * sat_score + 0.3 * var_score + 0.3 * min(emb_score, 1.0)

def top_rois(scores: list[TileScore], k: int = 50) -> list[TileScore]:
    return sorted(scores, key=lambda t: t.score, reverse=True)[:k]
