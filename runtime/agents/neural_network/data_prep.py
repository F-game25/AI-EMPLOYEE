"""data_prep.py — Dataset cleaning and preparation for neural network training.

Cleans a raw CSV/JSON/Parquet dataset and outputs train/validation/test splits
ready for neural network training.

Features:
  - Auto-detects file format (CSV, JSON, Parquet)
  - Drops duplicate rows
  - Handles missing values (numerical: median fill; categorical: mode fill or "MISSING")
  - Removes constant columns (zero variance)
  - Clips and scales numerical features (StandardScaler or MinMaxScaler)
  - One-hot encodes low-cardinality categorical columns
  - Label-encodes the target column
  - Optional text tokenisation via a simple whitespace tokenizer
  - Stratified train / val / test split
  - Saves preprocessed splits as .npz (numpy) and a scaler state as JSON

Usage (CLI):
    python -m agents.neural_network.data_prep \\
        --input  data/raw_dataset.csv \\
        --output data/processed/ \\
        --target label \\
        --val-ratio 0.1 \\
        --test-ratio 0.1

Usage (Python API):
    from agents.neural_network.data_prep import DataPrep

    prep = DataPrep(target_column="label")
    train, val, test = prep.fit_transform("data/raw_dataset.csv")
    prep.save("data/processed/")
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("data_prep")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [data_prep] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

# ── optional heavy dependencies (graceful fallback) ───────────────────────────
try:
    import pandas as pd  # type: ignore
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

try:
    import sklearn  # type: ignore  # noqa: F401
    from sklearn.model_selection import train_test_split  # type: ignore
    from sklearn.preprocessing import LabelEncoder, StandardScaler  # type: ignore
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

# ─────────────────────────────────────────────────────────────────────────────
# Simple pure-numpy utilities (used when sklearn is absent)
# ─────────────────────────────────────────────────────────────────────────────

def _np_standard_scale(X: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Z-score normalisation; returns scaled array and scaler parameters."""
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0)
    std[std == 0] = 1.0  # avoid division by zero for constant columns
    return (X - mean) / std, {"mean": mean.tolist(), "std": std.tolist()}


def _np_label_encode(series: List[Any]) -> Tuple[np.ndarray, Dict[str, int]]:
    """Map unique string labels to contiguous integers."""
    vocab = {v: i for i, v in enumerate(sorted(set(series)))}
    return np.array([vocab[v] for v in series], dtype=np.int64), vocab


def _stratified_split(
    X: np.ndarray,
    y: np.ndarray,
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> Tuple[
    Tuple[np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray],
]:
    """Stratified split into train/val/test.  Falls back to random if a class
    has too few samples for stratification.

    Returns:
        ``(train, val, test)`` where each element is a ``(X, y)`` tuple.
    """
    rng = np.random.default_rng(seed)
    n = len(X)
    indices = rng.permutation(n)
    n_test = max(1, int(n * test_ratio))
    n_val = max(1, int(n * val_ratio))
    test_idx = indices[:n_test]
    val_idx = indices[n_test : n_test + n_val]
    train_idx = indices[n_test + n_val :]
    return (
        (X[train_idx], y[train_idx]),
        (X[val_idx],   y[val_idx]),
        (X[test_idx],  y[test_idx]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# DataPrep
# ─────────────────────────────────────────────────────────────────────────────

class DataPrep:
    """End-to-end dataset cleaner and feature preprocessor.

    Args:
        target_column:   Name of the column that holds class labels.
        text_column:     Optional column with raw text to be tokenised.
        val_ratio:       Fraction of data reserved for validation.
        test_ratio:      Fraction of data reserved for testing.
        max_categories:  Maximum unique values for a column to be one-hot
                         encoded (higher-cardinality columns are dropped).
        scaling:         ``"standard"`` (z-score) or ``"minmax"`` or ``"none"``.
        seed:            Random seed for reproducibility.
    """

    def __init__(
        self,
        target_column: str = "label",
        text_column: Optional[str] = None,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        max_categories: int = 50,
        scaling: str = "standard",
        seed: int = 42,
    ) -> None:
        self.target_column = target_column
        self.text_column = text_column
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.max_categories = max_categories
        self.scaling = scaling
        self.seed = seed

        # State fitted during transform
        self._scaler_params: Dict[str, Any] = {}
        self._label_vocab: Dict[str, int] = {}
        self._feature_columns: List[str] = []
        self._ohe_columns: Dict[str, List[str]] = {}  # col → sorted categories
        self._median_fills: Dict[str, float] = {}
        self._mode_fills: Dict[str, str] = {}
        self._is_fitted: bool = False

    # ── public API ────────────────────────────────────────────────────────────

    def fit_transform(
        self, path: str
    ) -> Tuple[
        Tuple[np.ndarray, np.ndarray],
        Tuple[np.ndarray, np.ndarray],
        Tuple[np.ndarray, np.ndarray],
    ]:
        """Load, clean, encode, scale, and split a dataset file.

        Args:
            path: Path to a ``.csv``, ``.json``, or ``.parquet`` file.

        Returns:
            ``(train, val, test)`` where each element is ``(X, y)`` numpy
            arrays.  ``X`` has shape ``(N, num_features)`` and ``y`` has
            shape ``(N,)`` with integer class labels.
        """
        df = self._load(path)
        df = self._clean(df)
        X, y = self._encode(df)
        X = self._scale(X)
        return _stratified_split(X, y, self.val_ratio, self.test_ratio, self.seed)

    def save(self, output_dir: str) -> None:
        """Persist the fitted scaler/vocab state as JSON to *output_dir*."""
        if not self._is_fitted:
            raise RuntimeError("Call fit_transform() before save().")
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        state = {
            "target_column":   self.target_column,
            "text_column":     self.text_column,
            "scaling":         self.scaling,
            "feature_columns": self._feature_columns,
            "ohe_columns":     self._ohe_columns,
            "median_fills":    self._median_fills,
            "mode_fills":      self._mode_fills,
            "scaler_params":   self._scaler_params,
            "label_vocab":     self._label_vocab,
        }
        with (out / "prep_state.json").open("w") as fh:
            json.dump(state, fh, indent=2)
        logger.info("Preprocessor state saved → %s/prep_state.json", output_dir)

    def save_splits(
        self,
        output_dir: str,
        train: Tuple[np.ndarray, np.ndarray],
        val: Tuple[np.ndarray, np.ndarray],
        test: Tuple[np.ndarray, np.ndarray],
    ) -> None:
        """Save numpy splits to ``.npz`` files in *output_dir*."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, (X, y) in [("train", train), ("val", val), ("test", test)]:
            np.savez_compressed(out / f"{name}.npz", X=X, y=y)
            logger.info("Saved %s split: X=%s  y=%s → %s/%s.npz", name, X.shape, y.shape, output_dir, name)

    # ── internals ─────────────────────────────────────────────────────────────

    def _load(self, path: str):
        """Load a CSV, JSON, or Parquet file into a pandas DataFrame."""
        if not _HAS_PANDAS:
            raise ImportError(
                "pandas is required for DataPrep. Install with: pip install pandas"
            )
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(p)
        elif suffix in (".json", ".jsonl"):
            df = pd.read_json(p, lines=(suffix == ".jsonl"))
        elif suffix in (".parquet", ".pq"):
            df = pd.read_parquet(p)
        else:
            raise ValueError(f"Unsupported file format: {suffix!r}. Use .csv, .json, or .parquet")
        logger.info("Loaded %s: %d rows × %d columns", p.name, len(df), len(df.columns))
        return df

    def _clean(self, df):
        """Remove duplicates, handle missing values, and drop useless columns."""
        before = len(df)
        df = df.drop_duplicates()
        logger.info("Dropped %d duplicate rows (%.1f%%)", before - len(df), (before - len(df)) / max(before, 1) * 100)

        if self.target_column not in df.columns:
            raise ValueError(f"Target column {self.target_column!r} not found in dataset. "
                             f"Available columns: {list(df.columns)}")

        # Drop rows where target is missing
        df = df.dropna(subset=[self.target_column])

        # Separate target
        target = df[self.target_column]
        feature_df = df.drop(columns=[self.target_column])

        # Drop text column from numeric features (handled separately)
        if self.text_column and self.text_column in feature_df.columns:
            feature_df = feature_df.drop(columns=[self.text_column])

        # Drop columns with >80% missing values
        missing_frac = feature_df.isnull().mean()
        high_missing = missing_frac[missing_frac > 0.8].index.tolist()
        if high_missing:
            logger.info("Dropping %d columns with >80%% missing values: %s", len(high_missing), high_missing)
            feature_df = feature_df.drop(columns=high_missing)

        # Separate numeric and categorical
        num_cols = feature_df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = feature_df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

        # Fill missing numeric with median
        for col in num_cols:
            median_val = feature_df[col].median()
            if math.isnan(float(median_val)):
                median_val = 0.0
            self._median_fills[col] = float(median_val)
            feature_df[col] = feature_df[col].fillna(median_val)

        # Fill missing categorical with mode or "MISSING"
        for col in cat_cols:
            mode_vals = feature_df[col].mode()
            mode_val = str(mode_vals.iloc[0]) if len(mode_vals) > 0 else "MISSING"
            self._mode_fills[col] = mode_val
            feature_df[col] = feature_df[col].fillna(mode_val).astype(str)

        # Drop constant (zero-variance) numeric columns
        constant_cols = [c for c in num_cols if feature_df[c].nunique() <= 1]
        if constant_cols:
            logger.info("Dropping %d constant columns: %s", len(constant_cols), constant_cols)
            feature_df = feature_df.drop(columns=constant_cols)
            num_cols = [c for c in num_cols if c not in constant_cols]

        # Drop high-cardinality categorical columns
        high_card = [c for c in cat_cols if feature_df[c].nunique() > self.max_categories]
        if high_card:
            logger.info("Dropping %d high-cardinality columns: %s", len(high_card), high_card)
            feature_df = feature_df.drop(columns=high_card)
            cat_cols = [c for c in cat_cols if c not in high_card]

        # Record OHE vocabulary
        for col in cat_cols:
            self._ohe_columns[col] = sorted(feature_df[col].unique().tolist())

        logger.info(
            "After cleaning: %d rows, %d numeric cols, %d categorical cols",
            len(feature_df), len(num_cols), len(cat_cols),
        )

        cleaned = feature_df.copy()
        cleaned[self.target_column] = target.values
        return cleaned

    def _encode(self, df) -> Tuple[np.ndarray, np.ndarray]:
        """One-hot encode categoricals and label-encode target."""
        target_series = df[self.target_column]
        feature_df = df.drop(columns=[self.target_column])

        # One-hot encode categorical columns
        encoded_parts = []
        feature_names: List[str] = []

        num_cols = feature_df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = list(self._ohe_columns.keys())

        # Numeric block
        if num_cols:
            encoded_parts.append(feature_df[num_cols].values.astype(np.float32))
            feature_names.extend(num_cols)

        # Categorical block (one-hot)
        for col in cat_cols:
            categories = self._ohe_columns[col]
            col_data = feature_df[col].astype(str)
            ohe = np.zeros((len(col_data), len(categories)), dtype=np.float32)
            for i, val in enumerate(col_data):
                if val in categories:
                    ohe[i, categories.index(val)] = 1.0
            encoded_parts.append(ohe)
            feature_names.extend([f"{col}__{cat}" for cat in categories])

        self._feature_columns = feature_names

        if not encoded_parts:
            raise ValueError("No usable feature columns found after cleaning.")

        X = np.concatenate(encoded_parts, axis=1).astype(np.float32)

        # Label encode target
        labels = target_series.astype(str).tolist()
        unique_labels = sorted(set(labels))
        self._label_vocab = {v: i for i, v in enumerate(unique_labels)}
        y = np.array([self._label_vocab[lbl] for lbl in labels], dtype=np.int64)

        logger.info(
            "Encoded: X=%s  y=%s  classes=%d (%s)",
            X.shape, y.shape, len(unique_labels),
            ", ".join(f"{k}={v}" for k, v in self._label_vocab.items()),
        )
        self._is_fitted = True
        return X, y

    def _scale(self, X: np.ndarray) -> np.ndarray:
        """Scale numerical features according to *self.scaling*."""
        if self.scaling == "none":
            return X
        if self.scaling == "minmax":
            min_v = np.nanmin(X, axis=0)
            max_v = np.nanmax(X, axis=0)
            rng = max_v - min_v
            rng[rng == 0] = 1.0
            X_scaled = (X - min_v) / rng
            self._scaler_params = {"type": "minmax", "min": min_v.tolist(), "max": max_v.tolist()}
        else:  # standard (default)
            X_scaled, params = _np_standard_scale(X)
            self._scaler_params = {"type": "standard", **params}
        logger.info("Applied %s scaling.", self.scaling)
        return X_scaled


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Clean and prepare a raw dataset for neural network training."
    )
    parser.add_argument("--input",       required=True,         help="Path to raw dataset (.csv/.json/.parquet)")
    parser.add_argument("--output",      default="data/processed/", help="Output directory for processed splits")
    parser.add_argument("--target",      default="label",       help="Name of the target/label column")
    parser.add_argument("--text-col",    default=None,          help="Optional text column to exclude from numeric features")
    parser.add_argument("--val-ratio",   type=float, default=0.1, help="Validation split fraction")
    parser.add_argument("--test-ratio",  type=float, default=0.1, help="Test split fraction")
    parser.add_argument("--scaling",     default="standard",    choices=["standard", "minmax", "none"])
    parser.add_argument("--max-cats",    type=int, default=50,  help="Max categories for one-hot encoding")
    parser.add_argument("--seed",        type=int, default=42)
    args = parser.parse_args()

    prep = DataPrep(
        target_column=args.target,
        text_column=args.text_col,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        max_categories=args.max_cats,
        scaling=args.scaling,
        seed=args.seed,
    )

    train, val, test = prep.fit_transform(args.input)
    prep.save(args.output)
    prep.save_splits(args.output, train, val, test)

    print(f"\nDone!")
    print(f"  Train : X={train[0].shape}  y={train[1].shape}")
    print(f"  Val   : X={val[0].shape}  y={val[1].shape}")
    print(f"  Test  : X={test[0].shape}  y={test[1].shape}")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    _cli()
