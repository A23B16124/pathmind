import httpx
from pathlib import Path

GDC_API = "https://api.gdc.cancer.gov"

async def search_tcga_slides(project: str, histology: str, limit: int = 20) -> list[dict]:
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [project]}},
            {"op": "in", "content": {"field": "cases.disease_type", "value": [histology]}},
            {"op": "in", "content": {"field": "data_format", "value": ["SVS"]}},
        ]
    }
    payload = {"filters": filters, "fields": "file_id,file_name,file_size", "size": limit, "format": "JSON"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{GDC_API}/files", json=payload)
        r.raise_for_status()
        hits = r.json()["data"]["hits"]
    return [{"file_id": h["file_id"], "file_name": h["file_name"], "file_size": h["file_size"]} for h in hits]

async def download_slide(file_id: str, dest_dir: str, token: str | None = None) -> Path:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    headers = {"X-Auth-Token": token} if token else {}
    async with httpx.AsyncClient(timeout=3600, headers=headers) as client:
        async with client.stream("GET", f"{GDC_API}/data/{file_id}") as r:
            r.raise_for_status()
            fname = r.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or f"{file_id}.svs"
            out_path = dest / fname
            with open(out_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
    return out_path
