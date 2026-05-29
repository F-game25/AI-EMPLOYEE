"""Segment Anything Model — local image segmentation.

Local-first: runs SAM ViT-B (~375MB) on the local GPU. The checkpoint auto-downloads
to state/models/sam/ on first use. Pipeline/predictor is cached. Supports three modes:
  - points  : segment around [x,y] click points
  - bboxes  : segment inside a [x0,y0,x1,y1] box
  - auto    : automatic mask generation over the whole image (default when no prompt)
Masks are returned as RLE-free compact summaries + a base64 PNG overlay so the UI can
render without shipping giant boolean arrays.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_SAM = None
_SAM_ERR: str | None = None
_MODEL_TYPE = os.getenv("SAM_MODEL_TYPE", "vit_b")
_CKPT_URLS = {
    "vit_b": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
    "vit_l": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth",
    "vit_h": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth",
}
_CKPT_NAMES = {"vit_b": "sam_vit_b_01ec64.pth", "vit_l": "sam_vit_l_0b3195.pth",
               "vit_h": "sam_vit_h_4b8939.pth"}


def _models_dir() -> Path:
    d = Path(os.getenv("AI_EMPLOYEE_REPO_DIR", ".")) / "state" / "models" / "sam"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_checkpoint() -> Path:
    ckpt = _models_dir() / _CKPT_NAMES[_MODEL_TYPE]
    if not ckpt.exists() or ckpt.stat().st_size < 1_000_000:
        logger.info("Downloading SAM checkpoint %s …", _MODEL_TYPE)
        urllib.request.urlretrieve(_CKPT_URLS[_MODEL_TYPE], ckpt)  # noqa: S310
    return ckpt


def _load_sam():
    """Lazy-load + cache the SAM model. Returns (sam, device, error)."""
    global _SAM, _SAM_ERR
    if _SAM is not None:
        import torch
        return _SAM, ("cuda" if torch.cuda.is_available() else "cpu"), None
    if _SAM_ERR is not None:
        return None, None, _SAM_ERR
    try:
        import torch
        from segment_anything import sam_model_registry
        ckpt = _ensure_checkpoint()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        sam = sam_model_registry[_MODEL_TYPE](checkpoint=str(ckpt))
        sam.to(device=device)
        _SAM = sam
        logger.info("SAM loaded: %s on %s", _MODEL_TYPE, device)
        return _SAM, device, None
    except Exception as e:  # noqa: BLE001
        _SAM_ERR = str(e)
        logger.error("SAM load failed: %s", e)
        return None, None, _SAM_ERR


def unload() -> bool:
    """Free the SAM model from GPU/RAM. Called by the lifecycle manager."""
    global _SAM, _SAM_ERR
    if _SAM is None:
        return False
    try:
        del _SAM
    except Exception:  # noqa: BLE001
        pass
    _SAM, _SAM_ERR = None, None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    return True


def is_loaded() -> bool:
    return _SAM is not None


def _decode_image(image_data):
    import cv2
    import numpy as np
    if image_data is None:
        return None
    if isinstance(image_data, str):
        if image_data.startswith("data:image"):
            raw = base64.b64decode(image_data.split(",", 1)[1])
            arr = np.frombuffer(raw, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(image_data)
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img
    return image_data


def _mask_overlay_b64(image, masks) -> str:
    """Render colored mask overlay on the image → base64 PNG."""
    import cv2
    import numpy as np
    overlay = image.copy()
    rng = np.random.default_rng(42)
    for m in masks:
        color = rng.integers(60, 255, size=3)
        overlay[m] = (0.5 * overlay[m] + 0.5 * color).astype(np.uint8)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def route_sam(request: dict) -> dict:
    """Segment an image. Modes: points, bboxes, or automatic (default)."""
    sam, device, err = _load_sam()
    if sam is None:
        return {"status": "unavailable", "arch": "SAM", "available": False,
                "reason": f"SAM unavailable: {err}"}

    image = _decode_image(request.get("image") or (request.get("images") or [None])[0])
    if image is None:
        return {"status": "error", "arch": "SAM", "error": "Failed to load image (provide 'image' or 'images')"}

    import numpy as np
    points = request.get("points")
    bboxes = request.get("bboxes")

    try:
        if points or bboxes:
            from segment_anything import SamPredictor
            predictor = SamPredictor(sam)
            predictor.set_image(image)
            if points:
                pc = np.array(points, dtype=np.float32)
                pl = np.array(request.get("labels") or [1] * len(points), dtype=np.float32)
                masks, scores, _ = predictor.predict(point_coords=pc, point_labels=pl, multimask_output=False)
            else:
                box = np.array(bboxes[0], dtype=np.float32)
                masks, scores, _ = predictor.predict(box=box, multimask_output=False)
            bool_masks = [m.astype(bool) for m in masks]
            mode = "points" if points else "bboxes"
            scores_list = scores.tolist()
        else:
            from segment_anything import SamAutomaticMaskGenerator
            gen = SamAutomaticMaskGenerator(sam, points_per_side=16)  # lighter for 8GB
            anns = gen.generate(image)
            anns = sorted(anns, key=lambda a: a["area"], reverse=True)[:25]
            bool_masks = [a["segmentation"].astype(bool) for a in anns]
            scores_list = [float(a.get("stability_score", 0.0)) for a in anns]
            mode = "auto"

        summaries = [{"id": i, "area": int(m.sum()), "score": (scores_list[i] if i < len(scores_list) else None)}
                     for i, m in enumerate(bool_masks)]
        return {"status": "success", "arch": "SAM", "provider": "segment-anything-local",
                "model": _MODEL_TYPE, "device": device, "mode": mode,
                "mask_count": len(bool_masks), "masks": summaries,
                "overlay": _mask_overlay_b64(image, bool_masks),
                "output": f"{len(bool_masks)} masks ({mode})"}
    except Exception as e:  # noqa: BLE001
        logger.error("route_sam failed: %s", e)
        return {"status": "error", "arch": "SAM", "error": str(e)}
