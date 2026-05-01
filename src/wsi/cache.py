import hashlib
import numpy as np
from pathlib import Path

class TileCache:
    def __init__(self, cache_dir: str = "/opt/pathmind/cache/tiles"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def key(self, slide_path: str, tile_size: int, level: int) -> str:
        return hashlib.sha1(f"{slide_path}:{tile_size}:{level}".encode()).hexdigest()

    def path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.npz"

    def save(self, key: str, tiles: list[np.ndarray]) -> None:
        np.savez_compressed(self.path(key), tiles=np.stack(tiles))

    def load(self, key: str) -> list[np.ndarray] | None:
        p = self.path(key)
        if not p.exists():
            return None
        data = np.load(p)
        return [data["tiles"][i] for i in range(len(data["tiles"]))]
