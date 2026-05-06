"""Segment Anything Model routing — image segmentation (STUB)."""
import logging

logger = logging.getLogger(__name__)


def route_sam(request: dict) -> dict:
    """Route to SAM (image segmentation). Requires ~2.4GB weights.

    This is a stub. To enable:
    1. Set NEURAL_BRAIN_SAM_ENABLED=true
    2. pip install segment-anything
    """
    try:
        try:
            from segment_anything import sam_model_registry, SamPredictor
        except ImportError:
            return {
                "status": "disabled",
                "reason": "segment_anything not installed. Run: pip install segment-anything",
            }

        import base64
        from pathlib import Path
        import numpy as np

        # Get or download SAM model
        checkpoint = "sam_vit_h_4b8939.pth"
        model_type = "vit_h"
        device = "cuda"  # Force CUDA or cpu if unavailable

        try:
            sam = sam_model_registry[model_type](checkpoint=checkpoint)
        except Exception:
            device = "cpu"
            sam = sam_model_registry[model_type](checkpoint=checkpoint)

        sam.to(device=device)
        predictor = SamPredictor(sam)

        # Load image
        image_data = request.get("image")
        if isinstance(image_data, str):
            if image_data.startswith("data:image"):
                # Base64 encoded
                image_array = np.frombuffer(
                    base64.b64decode(image_data.split(",")[1]), dtype=np.uint8
                )
                import cv2

                image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            else:
                # File path
                import cv2

                image = cv2.imread(image_data)
        else:
            image = image_data

        if image is None:
            return {"status": "error", "error": "Failed to load image"}

        predictor.set_image(image)

        # Get prompts
        points = request.get("points")  # List of [x, y] coords
        labels = request.get("labels")  # List of 0 (negative) or 1 (positive)
        bboxes = request.get("bboxes")  # List of [x0, y0, x1, y1]

        if not any([points, bboxes]):
            return {"status": "error", "error": "Missing points or bboxes"}

        # Predict
        if points:
            points_array = np.array(points, dtype=np.float32)
            labels_array = np.array(labels or [1] * len(points), dtype=np.float32)
            masks, scores, _ = predictor.predict(
                point_coords=points_array,
                point_labels=labels_array,
                multimask_output=False,
            )
        else:
            input_box = np.array(bboxes[0], dtype=np.float32)
            masks, scores, _ = predictor.predict(
                box=input_box,
                multimask_output=False,
            )

        return {
            "status": "success",
            "output": {
                "masks": masks.astype(np.uint8).tolist(),
                "scores": scores.tolist(),
            },
            "provider": "sam",
            "model": model_type,
        }

    except Exception as e:
        logger.error(f"route_sam failed: {e}")
        return {"status": "error", "error": str(e)}
