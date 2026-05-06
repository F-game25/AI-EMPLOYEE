"""Masked Language Model routing — embeddings + masked prediction."""
import logging

logger = logging.getLogger(__name__)


def route_mlm(request: dict) -> dict:
    """Route to MLM (all-MiniLM-L6-v2 embeddings + masked fill)."""
    task = request.get("task", "embed")

    if task == "embed":
        return _embed(request)
    elif task == "fill_mask":
        return _fill_mask(request)
    else:
        return {"status": "error", "error": f"Unknown MLM task: {task}"}


def _embed(request: dict) -> dict:
    """Generate embeddings for texts."""
    try:
        from runtime.neural_brain.memory.embedding_provider import EmbeddingProvider

        texts = request.get("texts", [])
        if not texts:
            return {"status": "error", "error": "Missing texts"}

        provider = EmbeddingProvider.get()
        embeddings = provider.encode(texts, convert_to_tensor=False)

        return {
            "status": "success",
            "embeddings": embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings,
            "provider": "sentence-transformers",
            "model": "all-MiniLM-L6-v2",
        }

    except Exception as e:
        logger.error(f"_embed failed: {e}")
        return {"status": "error", "error": str(e)}


def _fill_mask(request: dict) -> dict:
    """Fill masked tokens (e.g., "The [MASK] is brown")."""
    try:
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        text = request.get("text", "")
        if "[MASK]" not in text:
            return {"status": "error", "error": "No [MASK] token in text"}

        model_name = "bert-base-uncased"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForMaskedLM.from_pretrained(model_name)

        inputs = tokenizer(text, return_tensors="pt")
        mask_token_index = (inputs["input_ids"] == tokenizer.mask_token_id)[0].nonzero(as_tuple=True)[0]

        outputs = model(**inputs)
        logits = outputs.logits
        mask_logits = logits[0, mask_token_index]
        top_tokens = mask_logits.topk(k=5)[1]
        predictions = tokenizer.decode(top_tokens)

        return {
            "status": "success",
            "predictions": predictions.split(),
            "provider": "huggingface",
            "model": model_name,
        }

    except Exception as e:
        logger.error(f"_fill_mask failed: {e}")
        return {"status": "error", "error": str(e)}
