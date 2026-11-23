"""E0: output-level check after full re-execution (the verifier regenerates the image).

Scores: pixel equality, LPIPS (AlexNet backbone, lpips v0.1) and DINOv2 CLS-token cosine.
Thresholds come from calibration (runbook §5); until then the rule returns raw scores with an
``inconclusive`` verdict unless thresholds are given.

Images are uint8 tensors [H, W, 3] (or [1, H, W, 3]), as saved by ComfyUI.
"""
from __future__ import annotations

from functools import lru_cache

import torch

from . import FAIL, INCONCLUSIVE, PASS, Verdict

DINO_MODEL = "facebook/dinov2-base"


def _hw3(img: torch.Tensor) -> torch.Tensor:
    return img[0] if img.ndim == 4 else img


@lru_cache(maxsize=1)
def _lpips():
    import lpips

    return lpips.LPIPS(net="alex", version="0.1", verbose=False).eval()


@lru_cache(maxsize=1)
def _dino():
    from transformers import AutoImageProcessor, AutoModel

    return AutoImageProcessor.from_pretrained(DINO_MODEL), AutoModel.from_pretrained(DINO_MODEL).eval()


@torch.no_grad()
def lpips_distance(a: torch.Tensor, b: torch.Tensor) -> float:
    to = lambda x: (_hw3(x).permute(2, 0, 1).float() / 127.5 - 1.0).unsqueeze(0)  # noqa: E731
    return float(_lpips()(to(a), to(b)).item())


@torch.no_grad()
def dino_cosine(a: torch.Tensor, b: torch.Tensor) -> float:
    proc, model = _dino()
    batch = proc(images=[_hw3(a).numpy(), _hw3(b).numpy()], return_tensors="pt")
    cls = model(**batch).last_hidden_state[:, 0]
    return float(torch.cosine_similarity(cls[0], cls[1], dim=0).item())


def scores(reference: torch.Tensor, candidate: torch.Tensor, with_models: bool = True) -> dict:
    a, b = _hw3(reference), _hw3(candidate)
    s = {"pixel_equal": bool(torch.equal(a, b)), "max_abs": int((a.int() - b.int()).abs().max())}
    if with_models:
        s["lpips"] = lpips_distance(a, b)
        s["dino_cosine"] = dino_cosine(a, b)
    return s


def e0(reference: torch.Tensor, candidate: torch.Tensor, th: dict | None = None) -> Verdict:
    """``th`` keys (from calibration): lpips_pass, lpips_fail, dino_pass, dino_fail.

    pass if LPIPS <= lpips_pass and DINO >= dino_pass; fail if LPIPS > lpips_fail or
    DINO < dino_fail; inconclusive otherwise (the draft's three-way rule).
    """
    s = scores(reference, candidate)
    if s["pixel_equal"]:
        return Verdict("E0", PASS, s)
    if not th or "lpips_pass" not in th:
        return Verdict("E0", INCONCLUSIVE, s, ["no calibrated E0 thresholds"])
    if s["lpips"] > th["lpips_fail"] or s["dino_cosine"] < th["dino_fail"]:
        return Verdict("E0", FAIL, s, ["output differs beyond the honest band"])
    if s["lpips"] <= th["lpips_pass"] and s["dino_cosine"] >= th["dino_pass"]:
        return Verdict("E0", PASS, s)
    return Verdict("E0", INCONCLUSIVE, s, ["between pass and fail thresholds"])
