import cv2
import numpy as np

def estimate_necrosis_pct(slide_tiles: list[np.ndarray]) -> dict:
    necrotic, total = 0, 0
    for tile in slide_tiles:
        if tile is None:
            continue
        total += 1
        hsv = cv2.cvtColor(tile, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1].mean()
        val = hsv[:, :, 2].mean()
        lap_var = cv2.Laplacian(cv2.cvtColor(tile, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
        if sat < 40 and val < 230 and lap_var < 200:
            necrotic += 1
    pct = round(100 * necrotic / total, 1) if total else 0.0
    return {
        "necrosis_pct": pct,
        "necrotic_tiles": necrotic,
        "total_tiles": total,
        "grade": "high" if pct > 30 else "moderate" if pct > 10 else "low",
    }
