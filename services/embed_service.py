"""
PathMind Embedding Service — UNI2-h + Virchow2 on ROCm GPU.
POST /embed  { model: "uni2"|"virchow2", tiles: [[H,W,3], ...] }
GET  /health
"""
import os, gc, time, logging
import numpy as np
import torch
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("embed")

DEVICE = "cuda"
MODEL_DIR = "/shared-docker/models"

_models: dict = {}


def _load_uni2():
    import timm
    kwargs = dict(
        model_name="vit_giant_patch14_224",
        img_size=224, patch_size=14, depth=24, num_heads=24,
        init_values=1e-5, embed_dim=1536, mlp_ratio=2.66667 * 2,
        num_classes=0, no_embed_class=True,
        mlp_layer=timm.layers.SwiGLUPacked, act_layer=torch.nn.SiLU,
        reg_tokens=8, dynamic_img_size=True,
    )
    m = timm.create_model(pretrained=False, **kwargs)
    state = torch.load(f"{MODEL_DIR}/uni2/pytorch_model.bin", map_location="cpu")
    m.load_state_dict(state, strict=True)
    m.eval().to(DEVICE)
    cfg = timm.data.resolve_model_data_config(m)
    t = timm.data.create_transform(**cfg, is_training=False)
    log.info("UNI2-h loaded — %dM params", sum(p.numel() for p in m.parameters()) // 1_000_000)
    return m, t


def _load_virchow2():
    import timm
    kwargs = dict(
        model_name="vit_huge_patch14_224",
        img_size=224, init_values=1e-5, num_classes=0,
        reg_tokens=4, mlp_ratio=5.3375, global_pool="",
        dynamic_img_size=True,
        mlp_layer=timm.layers.SwiGLUPacked,
        act_layer=torch.nn.SiLU,
    )
    m = timm.create_model(pretrained=False, **kwargs)
    weights_path = f"{MODEL_DIR}/virchow2/pytorch_model.bin"
    if not os.path.exists(weights_path):
        weights_path = f"{MODEL_DIR}/virchow2/model.safetensors"
        from safetensors.torch import load_file
        state = load_file(weights_path, device="cpu")
    else:
        state = torch.load(weights_path, map_location="cpu")
    m.load_state_dict(state, strict=True)
    m.eval().to(DEVICE)
    from torchvision import transforms
    t = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    log.info("Virchow2 loaded — %dM params", sum(p.numel() for p in m.parameters()) // 1_000_000)
    return m, t


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading UNI2-h...")
    _models["uni2"] = _load_uni2()
    log.info("Loading Virchow2...")
    _models["virchow2"] = _load_virchow2()
    log.info("Both models ready.")
    yield
    _models.clear()
    gc.collect()
    torch.cuda.empty_cache()


app = FastAPI(title="PathMind Embed Service", lifespan=lifespan)


class EmbedRequest(BaseModel):
    model: Literal["uni2", "virchow2"] = "uni2"
    tiles: List[List[List[List[int]]]]  # [N, H, W, 3]
    batch_size: int = 128


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    n_tiles: int
    elapsed_ms: float


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    if req.model not in _models:
        raise HTTPException(503, f"Model {req.model} not loaded")
    model, transforms = _models[req.model]
    from PIL import Image
    t0 = time.perf_counter()
    tiles_np = np.array(req.tiles, dtype=np.uint8)
    all_embs = []
    for i in range(0, len(tiles_np), req.batch_size):
        batch = torch.stack([transforms(Image.fromarray(t)) for t in tiles_np[i:i + req.batch_size]]).to(DEVICE)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            emb = model(batch)
            if emb.ndim == 3:
                emb = emb[:, 0]
        all_embs.append(emb.float().cpu().numpy())
    embeddings = np.concatenate(all_embs, axis=0)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("Embedded %d tiles with %s in %.0fms", len(tiles_np), req.model, elapsed_ms)
    return EmbedResponse(
        embeddings=embeddings.tolist(),
        model=req.model,
        n_tiles=len(tiles_np),
        elapsed_ms=round(elapsed_ms, 1),
    )


@app.get("/health")
def health():
    loaded = list(_models.keys())
    gpu_mem = {}
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(i)
            gpu_mem[f"gpu{i}"] = {"free_gb": round(free / 1e9, 1), "total_gb": round(total / 1e9, 1)}
    return {"status": "ok", "models_loaded": loaded, "gpu": gpu_mem}
