from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

app = FastAPI()
_slides = {}


def _get(slide_id: str):
    if slide_id not in _slides:
        raise HTTPException(404, f"slide {slide_id} not loaded")
    return _slides[slide_id]


@app.post("/slides/{slide_id}/load")
def load_slide(slide_id: str, path: str):
    import pyvips
    _slides[slide_id] = pyvips.Image.new_from_file(path, access="sequential")
    img = _slides[slide_id]
    return {"width": img.width, "height": img.height}


@app.get("/slides/{slide_id}.dzi")
def dzi_manifest(slide_id: str):
    img = _get(slide_id)
    xml = ('<?xml version="1.0" encoding="utf-8"?>'
           '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" Format="jpeg" Overlap="1" TileSize="256">'
           f'<Size Width="{img.width}" Height="{img.height}"/></Image>')
    return Response(xml, media_type="application/xml")


@app.get("/slides/{slide_id}_files/{level}/{col}_{row}.jpeg")
def get_tile(slide_id: str, level: int, col: int, row: int):
    img = _get(slide_id)
    scale = max(1, img.width // (256 * (2 ** level)))
    size = 256
    x, y = col * size * scale, row * size * scale
    w, h = min(size * scale, img.width - x), min(size * scale, img.height - y)
    if w <= 0 or h <= 0:
        raise HTTPException(404, "tile out of bounds")
    tile = img.extract_area(x, y, w, h)
    if scale > 1:
        tile = tile.resize(1.0 / scale)
    return Response(tile.write_to_buffer(".jpg[Q=80]"), media_type="image/jpeg")
