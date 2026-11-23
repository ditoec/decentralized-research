"""E0-N: faithful reproduction of the deployed NicheImage SN23 output check.

Source (MIT licence, Copyright (c) 2023 Opentensor), repository SocialTensor/SocialTensorSubnet
at commit a4a2461b86d8eacc32674969985d032e0ef94fb0:

* services/rewarding/cosine_similarity_compare.py: ``CosineSimilarityReward``
  (timm ``vit_base_patch16_clip_384.laion2b_ft_in12k_in1k``, ``num_classes=0``; reward 1.0 if
  cos > 0.9, ``(cos + (1 - 0.9)) ** 3`` if cos > 0.4, else 0.0; ``nsfw_filter`` black-image rule);
* services/rewarding/hash_compare.py: ``matching_image`` (average_hash, hash_size=8, Hamming
  distance <= 6).

``nsfw_filter`` compares hash_size=6 hashes of the two images with a hash_size=8 hash of a black
image, so the strings never match and the filter never fires. We reproduce that behaviour as
deployed (``faithful_nsfw=True``) and note it in the paper; ``faithful_nsfw=False`` applies the
evidently intended same-size comparison, for reference only.

Acceptance for the attack tables: full reward (1.0), i.e. CLIP cosine > 0.9.
"""
from __future__ import annotations

from functools import lru_cache

import torch

from . import FAIL, PASS, Verdict

CLIP_MODEL = "vit_base_patch16_clip_384.laion2b_ft_in12k_in1k"
THRESHOLD = 0.9


def _pil(img: torch.Tensor):
    from PIL import Image

    a = img[0] if img.ndim == 4 else img
    return Image.fromarray(a.numpy())


@lru_cache(maxsize=1)
def _clip():
    import timm

    model = timm.create_model(CLIP_MODEL, pretrained=True, num_classes=0).eval()
    cfg = timm.data.resolve_model_data_config(model)
    return model, timm.data.create_transform(**cfg, is_training=False)


@torch.inference_mode()
def clip_cosine(validator_image: torch.Tensor, miner_image: torch.Tensor) -> float:
    model, tf = _clip()
    v = model(tf(_pil(validator_image)).unsqueeze(0))
    m = model(tf(_pil(miner_image)).unsqueeze(0))
    return float(torch.nn.functional.cosine_similarity(v, m).item())


def reward_from_cosine(cos: float, threshold: float = THRESHOLD) -> float:
    if cos > threshold:
        return 1.0
    if cos > 0.4:
        return (cos + (1 - threshold)) ** 3
    return 0.0


def nsfw_filter(validator_image, miner_image, faithful_nsfw: bool = True) -> int:
    import imagehash
    from PIL import Image

    v, m = _pil(validator_image), _pil(miner_image)
    W, H = v.size
    size = 6
    vh, mh = str(imagehash.average_hash(v, hash_size=size)), str(imagehash.average_hash(m, hash_size=size))
    black = str(imagehash.average_hash(Image.new("RGB", (W, H), color="black"), hash_size=8 if faithful_nsfw else size))
    if vh != black and mh == black:
        return 1
    if vh == black and mh != black:
        return 2
    return 0


def phash_match(validator_image, miner_image) -> tuple[bool, int]:
    import imagehash

    d = imagehash.average_hash(_pil(miner_image), hash_size=8) - imagehash.average_hash(_pil(validator_image), hash_size=8)
    return d <= 6, int(d)


def e0n(validator_image: torch.Tensor, miner_image: torch.Tensor, faithful_nsfw: bool = True) -> Verdict:
    flag = nsfw_filter(validator_image, miner_image, faithful_nsfw)
    match, hamming = phash_match(validator_image, miner_image)
    if flag:
        reward, cos = (-5.0 if flag == 2 else 0.0), None
    else:
        cos = clip_cosine(validator_image, miner_image)
        reward = reward_from_cosine(cos)
    s = {"clip_cosine": cos, "reward": reward, "nsfw_flag": flag, "phash_hamming": hamming, "phash_match": match}
    ok = reward == 1.0
    return Verdict("E0-N", PASS if ok else FAIL, s, [] if ok else [f"reward {reward:.3f} < 1.0"])
