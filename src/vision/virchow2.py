import torch
import numpy as np

MODEL_PATH = "/opt/pathmind/models/virchow2"


def load_virchow2(device: str = "cuda"):
    import timm
    model = timm.create_model(
        "hf-hub:paige-ai/Virchow2", pretrained=True, cache_dir=MODEL_PATH,
        mlp_layer=timm.layers.SwiGLUPacked, act_layer=torch.nn.SiLU,
    )
    model.eval().to(device)
    cfg = timm.data.resolve_model_data_config(model)
    return model, timm.data.create_transform(**cfg, is_training=False)


def encode_tiles(tiles_rgb, model, transforms, device: str = "cuda", batch_size: int = 256):
    from PIL import Image
    all_embs = []
    for i in range(0, len(tiles_rgb), batch_size):
        batch = torch.stack([transforms(Image.fromarray(t)) for t in tiles_rgb[i:i + batch_size]]).to(device)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            emb = model(batch)[:, 0]
        all_embs.append(emb.float().cpu().numpy())
    return np.concatenate(all_embs, axis=0)
