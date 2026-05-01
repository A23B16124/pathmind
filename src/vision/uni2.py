import torch
import numpy as np

MODEL_PATH = "/opt/pathmind/models/uni2"


def load_uni2(device: str = "cuda"):
    import timm
    model = timm.create_model(
        "hf-hub:MahmoodLab/UNI2-h", pretrained=True, cache_dir=MODEL_PATH,
        init_values=1e-5, dynamic_img_size=True,
    )
    model.eval().to(device)
    cfg = timm.data.resolve_model_data_config(model)
    return model, timm.data.create_transform(**cfg, is_training=False)


def aggregate_slide(patch_embeddings: np.ndarray, device: str = "cuda") -> np.ndarray:
    return torch.tensor(patch_embeddings, dtype=torch.float32).to(device).mean(dim=0).cpu().numpy()
