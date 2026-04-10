"""nlp_transformer.py — PyTorch text classification with a Transformer encoder.

Implements a complete NLP pipeline for multi-class text classification:
  • SimpleTokenizer  — whitespace/punctuation tokenizer + vocabulary builder
  • TransformerClassifier — sinusoidal positional encoding + stacked
                            TransformerEncoder layers + pooling + linear head
  • NLPTrainer        — training loop with cross-entropy loss, AdamW optimiser,
                        gradient clipping, and per-epoch validation
  • Utilities         — encode_batch(), decode_prediction()

Architecture
────────────
  Input tokens (B, L)
    │
  nn.Embedding (vocab_size, d_model)
    │
  Sinusoidal PositionalEncoding
    │
  TransformerEncoderLayer × num_layers
    │
  Mean pooling  (B, d_model)
    │
  Dropout
    │
  nn.Linear (d_model, num_classes)  → logits (B, num_classes)

Usage (CLI):
    python -m agents.neural_network.nlp_transformer \\
        --train data/train.jsonl \\
        --val   data/val.jsonl   \\
        --epochs 5 \\
        --output models/nlp_model.pth

Usage (Python API):
    from agents.neural_network.nlp_transformer import SimpleTokenizer, TransformerClassifier, NLPTrainer

    tokenizer = SimpleTokenizer(max_vocab=10_000, max_len=128)
    tokenizer.fit(train_texts)

    model = TransformerClassifier(
        vocab_size=tokenizer.vocab_size,
        num_classes=4,
    )

    trainer = NLPTrainer(model, tokenizer)
    trainer.train(train_texts, train_labels, val_texts, val_labels, epochs=5)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("nlp_transformer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [nlp_transformer] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

_PAD = "<PAD>"
_UNK = "<UNK>"


class SimpleTokenizer:
    """Whitespace + punctuation tokenizer with vocabulary management.

    Args:
        max_vocab: Maximum vocabulary size (most-frequent tokens kept).
        max_len:   Maximum token sequence length (longer sequences truncated,
                   shorter ones padded).
        lowercase: Whether to lower-case all input text.
    """

    def __init__(
        self,
        max_vocab: int = 10_000,
        max_len: int = 128,
        lowercase: bool = True,
    ) -> None:
        self.max_vocab = max_vocab
        self.max_len = max_len
        self.lowercase = lowercase

        self._word2idx: Dict[str, int] = {_PAD: 0, _UNK: 1}
        self._idx2word: Dict[int, str] = {0: _PAD, 1: _UNK}
        self._is_fitted: bool = False

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def vocab_size(self) -> int:
        return len(self._word2idx)

    @property
    def pad_id(self) -> int:
        return self._word2idx[_PAD]

    def fit(self, texts: List[str]) -> "SimpleTokenizer":
        """Build vocabulary from a list of strings.

        Counts token frequencies and keeps the top *max_vocab - 2* tokens
        (leaving space for PAD and UNK).
        """
        from collections import Counter
        freq: Counter = Counter()
        for text in texts:
            freq.update(self._tokenize(text))

        top_tokens = [tok for tok, _ in freq.most_common(self.max_vocab - 2)]
        for tok in top_tokens:
            if tok not in self._word2idx:
                idx = len(self._word2idx)
                self._word2idx[tok] = idx
                self._idx2word[idx] = tok

        self._is_fitted = True
        logger.info("Tokenizer fitted: vocab_size=%d  max_len=%d", self.vocab_size, self.max_len)
        return self

    def encode(self, text: str) -> List[int]:
        """Convert a single text string to a padded/truncated id list."""
        tokens = self._tokenize(text)[: self.max_len]
        ids = [self._word2idx.get(t, self._word2idx[_UNK]) for t in tokens]
        # Pad
        ids += [self._word2idx[_PAD]] * (self.max_len - len(ids))
        return ids

    def encode_batch(self, texts: List[str]) -> "torch.Tensor":
        """Encode a list of texts into a (N, max_len) int64 tensor."""
        if not _HAS_TORCH:
            raise ImportError("torch is required. Install with: pip install torch")
        ids = [self.encode(t) for t in texts]
        return torch.tensor(ids, dtype=torch.long)

    def save(self, path: str) -> None:
        """Save vocabulary to a JSON file."""
        with Path(path).open("w") as fh:
            json.dump({"word2idx": self._word2idx, "max_len": self.max_len,
                       "max_vocab": self.max_vocab, "lowercase": self.lowercase}, fh)
        logger.info("Tokenizer saved → %s", path)

    @classmethod
    def load(cls, path: str) -> "SimpleTokenizer":
        """Load a previously saved tokenizer."""
        with Path(path).open() as fh:
            data = json.load(fh)
        tok = cls(max_vocab=data["max_vocab"], max_len=data["max_len"], lowercase=data["lowercase"])
        tok._word2idx = data["word2idx"]
        tok._idx2word = {int(v): k for k, v in data["word2idx"].items()}
        tok._is_fitted = True
        return tok

    # ── internals ─────────────────────────────────────────────────────────────

    def _tokenize(self, text: str) -> List[str]:
        if self.lowercase:
            text = text.lower()
        # Split on whitespace and punctuation
        tokens = re.findall(r"\b\w+\b", text)
        return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Positional Encoding
# ─────────────────────────────────────────────────────────────────────────────

class PositionalEncoding(nn.Module):
    """Fixed sinusoidal positional encoding (Vaswani et al. 2017)."""

    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)  # (max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)  # (max_len, 1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float) * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        # Handle both even and odd d_model: cos terms use same div_term length
        pe[:, 1::2] = torch.cos(position * div_term[: pe[:, 1::2].shape[1]])
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        # x: (B, L, d_model)
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)


# ─────────────────────────────────────────────────────────────────────────────
# Transformer Classifier
# ─────────────────────────────────────────────────────────────────────────────

class TransformerClassifier(nn.Module):
    """Text classification model based on a Transformer encoder.

    Args:
        vocab_size:  Size of the input token vocabulary.
        num_classes: Number of output classes.
        d_model:     Embedding / hidden dimension (must be divisible by nhead).
        nhead:       Number of attention heads.
        num_layers:  Number of stacked TransformerEncoder layers.
        dim_feedforward: Inner dimension of the feed-forward sub-layer.
        dropout:     Dropout probability applied throughout the model.
        max_len:     Maximum sequence length (for positional encoding).
    """

    def __init__(
        self,
        vocab_size: int,
        num_classes: int,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        max_len: int = 128,
    ) -> None:
        if not _HAS_TORCH:
            raise ImportError("torch is required. Install with: pip install torch")
        super().__init__()

        self.d_model = d_model
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_enc = PositionalEncoding(d_model, max_len=max_len, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,  # (B, L, d_model) convention
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.dropout = nn.Dropout(p=dropout)
        self.classifier = nn.Linear(d_model, num_classes)

        self._init_weights()

    # ── initialisation ────────────────────────────────────────────────────────

    def _init_weights(self) -> None:
        nn.init.normal_(self.embedding.weight, mean=0.0, std=0.02)
        nn.init.xavier_uniform_(self.classifier.weight)
        if self.classifier.bias is not None:
            nn.init.zeros_(self.classifier.bias)

    # ── forward ───────────────────────────────────────────────────────────────

    def forward(
        self,
        input_ids: "torch.Tensor",
        padding_mask: Optional["torch.Tensor"] = None,
    ) -> "torch.Tensor":
        """Forward pass.

        Args:
            input_ids:    (B, L) integer token ids.
            padding_mask: (B, L) boolean mask where ``True`` marks padding
                          positions to be ignored.  If *None* it is derived
                          automatically from ``input_ids == 0``.

        Returns:
            logits of shape ``(B, num_classes)``.
        """
        if padding_mask is None:
            padding_mask = input_ids == 0  # (B, L)

        # (B, L) → (B, L, d_model)
        x = self.embedding(input_ids) * math.sqrt(self.d_model)
        x = self.pos_enc(x)

        # Transformer encoder
        x = self.transformer_encoder(x, src_key_padding_mask=padding_mask)  # (B, L, d_model)

        # Mean pooling over non-padding positions
        mask_float = (~padding_mask).unsqueeze(-1).float()  # (B, L, 1)
        x = (x * mask_float).sum(dim=1) / mask_float.sum(dim=1).clamp(min=1.0)  # (B, d_model)

        x = self.dropout(x)
        return self.classifier(x)  # (B, num_classes)

    @torch.no_grad()
    def predict(
        self,
        input_ids: "torch.Tensor",
    ) -> Tuple["torch.Tensor", "torch.Tensor"]:
        """Return ``(predicted_class, confidence)`` for a batch.

        Args:
            input_ids: (B, L) integer token ids.

        Returns:
            ``(class_indices, confidence_scores)`` both of shape ``(B,)``.
        """
        was_training = self.training
        self.eval()
        logits = self(input_ids)
        probs = torch.softmax(logits, dim=-1)
        pred = probs.argmax(dim=-1)
        conf = probs.max(dim=-1).values
        if was_training:
            self.train()
        return pred, conf


# ─────────────────────────────────────────────────────────────────────────────
# NLP Trainer
# ─────────────────────────────────────────────────────────────────────────────

class NLPTrainer:
    """Training and evaluation wrapper for :class:`TransformerClassifier`.

    Args:
        model:         The TransformerClassifier to train.
        tokenizer:     A fitted SimpleTokenizer.
        lr:            Initial learning rate for AdamW.
        batch_size:    Mini-batch size.
        max_grad_norm: Gradient clipping threshold.
        device:        ``"auto"`` selects CUDA > MPS > CPU automatically.
    """

    def __init__(
        self,
        model: "TransformerClassifier",
        tokenizer: "SimpleTokenizer",
        lr: float = 2e-4,
        batch_size: int = 32,
        max_grad_norm: float = 1.0,
        device: str = "auto",
    ) -> None:
        if not _HAS_TORCH:
            raise ImportError("torch is required. Install with: pip install torch")

        self.model = model
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.max_grad_norm = max_grad_norm

        # Device selection
        if device == "auto":
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = torch.device("mps")
            else:
                self.device = torch.device("cpu")
        else:
            self.device = torch.device(device)

        self.model.to(self.device)
        self.optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-2)
        self.loss_fn = nn.CrossEntropyLoss()

        logger.info("NLPTrainer ready on device: %s", self.device)

    # ── public API ────────────────────────────────────────────────────────────

    def train(
        self,
        train_texts: List[str],
        train_labels: List[int],
        val_texts: Optional[List[str]] = None,
        val_labels: Optional[List[int]] = None,
        epochs: int = 5,
    ) -> List[Dict]:
        """Run the training loop.

        Args:
            train_texts:  List of raw text strings for training.
            train_labels: Corresponding integer class labels.
            val_texts:    Optional validation texts.
            val_labels:   Optional validation labels.
            epochs:       Number of full passes over the training set.

        Returns:
            List of per-epoch metric dicts with keys
            ``epoch``, ``train_loss``, ``train_acc``, ``val_loss``, ``val_acc``.
        """
        train_loader = self._make_loader(train_texts, train_labels, shuffle=True)
        val_loader = self._make_loader(val_texts, val_labels, shuffle=False) if val_texts else None

        history = []
        for epoch in range(1, epochs + 1):
            train_loss, train_acc = self._run_epoch(train_loader, train=True)
            row: Dict = {"epoch": epoch, "train_loss": train_loss, "train_acc": train_acc}

            if val_loader:
                val_loss, val_acc = self._run_epoch(val_loader, train=False)
                row["val_loss"] = val_loss
                row["val_acc"] = val_acc
                logger.info(
                    "Epoch %d/%d — loss=%.4f acc=%.4f | val_loss=%.4f val_acc=%.4f",
                    epoch, epochs, train_loss, train_acc, val_loss, val_acc,
                )
            else:
                logger.info("Epoch %d/%d — loss=%.4f acc=%.4f", epoch, epochs, train_loss, train_acc)

            history.append(row)
        return history

    def evaluate(
        self,
        texts: List[str],
        labels: List[int],
    ) -> Dict:
        """Compute loss and accuracy on an arbitrary text/label list."""
        loader = self._make_loader(texts, labels, shuffle=False)
        loss, acc = self._run_epoch(loader, train=False)
        return {"loss": loss, "accuracy": acc}

    def save(self, path: str) -> None:
        """Save model weights to disk."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), path)
        logger.info("NLP model saved → %s", path)

    def load(self, path: str) -> None:
        """Load model weights from disk."""
        self.model.load_state_dict(
            torch.load(path, map_location=self.device, weights_only=True)
        )
        logger.info("NLP model loaded ← %s", path)

    # ── internals ─────────────────────────────────────────────────────────────

    def _make_loader(
        self,
        texts: Optional[List[str]],
        labels: Optional[List[int]],
        shuffle: bool,
    ) -> Optional["DataLoader"]:
        if texts is None or labels is None:
            return None
        input_ids = self.tokenizer.encode_batch(texts).to(self.device)
        label_t = torch.tensor(labels, dtype=torch.long).to(self.device)
        dataset = TensorDataset(input_ids, label_t)
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=shuffle)

    def _run_epoch(
        self,
        loader: "DataLoader",
        train: bool,
    ) -> Tuple[float, float]:
        self.model.train(train)
        total_loss = 0.0
        correct = 0
        total = 0

        ctx = torch.enable_grad() if train else torch.no_grad()
        with ctx:
            for input_ids, labels in loader:
                logits = self.model(input_ids)
                loss = self.loss_fn(logits, labels)

                if train:
                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
                    self.optimizer.step()

                total_loss += loss.item() * len(labels)
                correct += (logits.argmax(dim=-1) == labels).sum().item()
                total += len(labels)

        avg_loss = total_loss / max(total, 1)
        accuracy = correct / max(total, 1)
        return avg_loss, accuracy


# ─────────────────────────────────────────────────────────────────────────────
# Convenience utilities
# ─────────────────────────────────────────────────────────────────────────────

def encode_batch(
    texts: List[str],
    tokenizer: "SimpleTokenizer",
) -> "torch.Tensor":
    """Encode *texts* using *tokenizer* and return a (N, max_len) tensor."""
    return tokenizer.encode_batch(texts)


def decode_prediction(
    pred_idx: int,
    label_vocab: Dict[str, int],
) -> str:
    """Convert a predicted class index back to its string label."""
    inv = {v: k for k, v in label_vocab.items()}
    return inv.get(pred_idx, f"class_{pred_idx}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _load_jsonl(path: str) -> Tuple[List[str], List[int], Dict[str, int]]:
    """Load a JSONL file with ``{"text": ..., "label": ...}`` records."""
    texts, raw_labels = [], []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            texts.append(str(obj["text"]))
            raw_labels.append(str(obj["label"]))

    unique = sorted(set(raw_labels))
    vocab = {v: i for i, v in enumerate(unique)}
    labels = [vocab[l] for l in raw_labels]
    return texts, labels, vocab


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Train a Transformer NLP text classifier."
    )
    parser.add_argument("--train",   required=True, help="Training JSONL file ({text, label})")
    parser.add_argument("--val",     default=None,  help="Validation JSONL file")
    parser.add_argument("--output",  default="models/nlp_model.pth", help="Where to save the trained model")
    parser.add_argument("--tokenizer-out", default="models/tokenizer.json", help="Where to save the tokenizer")
    parser.add_argument("--epochs",  type=int, default=5)
    parser.add_argument("--lr",      type=float, default=2e-4)
    parser.add_argument("--batch",   type=int, default=32)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--nhead",   type=int, default=4)
    parser.add_argument("--layers",  type=int, default=2)
    parser.add_argument("--max-len", type=int, default=128)
    parser.add_argument("--vocab",   type=int, default=10_000)
    args = parser.parse_args()

    if not _HAS_TORCH:
        print("ERROR: PyTorch is not installed. Run: pip install torch", file=sys.stderr)
        sys.exit(1)

    train_texts, train_labels, label_vocab = _load_jsonl(args.train)
    val_texts, val_labels = None, None
    if args.val:
        val_texts, val_labels, _ = _load_jsonl(args.val)

    num_classes = len(label_vocab)
    logger.info("Classes (%d): %s", num_classes, label_vocab)

    tokenizer = SimpleTokenizer(max_vocab=args.vocab, max_len=args.max_len)
    tokenizer.fit(train_texts)

    model = TransformerClassifier(
        vocab_size=tokenizer.vocab_size,
        num_classes=num_classes,
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.layers,
        max_len=args.max_len,
    )

    trainer = NLPTrainer(model, tokenizer, lr=args.lr, batch_size=args.batch)
    history = trainer.train(train_texts, train_labels, val_texts, val_labels, epochs=args.epochs)
    trainer.save(args.output)
    tokenizer.save(args.tokenizer_out)

    print(f"\nTraining complete. Final epoch: {history[-1]}")


if __name__ == "__main__":
    _cli()
