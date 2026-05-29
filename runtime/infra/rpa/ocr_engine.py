"""OCR engine — Tesseract primary, cloud vision fallback."""
from __future__ import annotations
import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import Image
    import io
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False

_OCR_API_URL = os.getenv("OCR_API_URL", "")


async def extract_text(image_bytes: bytes, lang: str = "eng") -> dict:
    """Return {text, confidence, ocr_engine, available}."""
    if _TESSERACT_OK:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
            words = [w for w, c in zip(data["text"], data["conf"]) if int(c) > 0 and w.strip()]
            confs = [int(c) for c in data["conf"] if int(c) > 0]
            text = " ".join(words)
            confidence = sum(confs) / len(confs) / 100 if confs else 0.0
            return {"text": text, "confidence": confidence, "ocr_engine": "tesseract", "available": True}
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)

    if _OCR_API_URL:
        try:
            import httpx
            payload = {"image": base64.b64encode(image_bytes).decode(), "lang": lang}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(_OCR_API_URL, json=payload)
                data = r.json()
                return {"text": data.get("text", ""), "confidence": data.get("confidence", 0.0),
                        "ocr_engine": "cloud", "available": True}
        except Exception as e:
            logger.warning("Cloud OCR failed: %s", e)

    return {"text": "", "confidence": 0.0, "ocr_engine": "none", "available": False}
