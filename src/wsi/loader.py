import numpy as np
import openslide
import cv2
from typing import Iterator

def iter_tissue_tiles(
    slide_path: str,
    tile_size: int = 256,
    level: int = 0,
    otsu_threshold: int = 15,
) -> Iterator[tuple[int, int, np.ndarray]]:
    slide = openslide.OpenSlide(slide_path)
    w, h = slide.level_dimensions[level]
    thumb = np.array(slide.get_thumbnail((w // tile_size, h // tile_size)).convert("RGB"))
    gray = cv2.cvtColor(thumb, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    for row in range(h // tile_size):
        for col in range(w // tile_size):
            if row >= mask.shape[0] or col >= mask.shape[1]:
                continue
            if mask[row, col] < otsu_threshold:
                continue
            tile_pil = slide.read_region((col * tile_size, row * tile_size), level, (tile_size, tile_size))
            yield row, col, np.array(tile_pil.convert("RGB"))
    slide.close()
