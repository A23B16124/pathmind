import os
import torch
import numpy as np
import timm

MODEL_PATH = '/opt/pathmind/models/uni2'

TIMM_KWARGS = dict(
    model_name='vit_giant_patch14_224',
    img_size=224, patch_size=14, depth=24, num_heads=24,
    init_values=1e-5, embed_dim=1536, mlp_ratio=2.66667 * 2,
    num_classes=0, no_embed_class=True,
    mlp_layer=timm.layers.SwiGLUPacked, act_layer=torch.nn.SiLU,
    reg_tokens=8, dynamic_img_size=True,
)


def load_uni2(device: str = 'cuda'):
    model = timm.create_model(pretrained=False, **TIMM_KWARGS)
    state = torch.load(os.path.join(MODEL_PATH, 'pytorch_model.bin'), map_location='cpu')
    model.load_state_dict(state, strict=True)
    model.eval().to(device)
    cfg = timm.data.resolve_model_data_config(model)
    return model, timm.data.create_transform(**cfg, is_training=False)


def aggregate_slide(patch_embeddings: np.ndarray, device: str = 'cuda') -> np.ndarray:
    return torch.tensor(patch_embeddings, dtype=torch.float32).to(device).mean(dim=0).cpu().numpy()
