"""tests/test_ml_components.py — Unit tests for the four new ML components.

Covers:
  1. data_prep.py   — DataPrep: cleaning, encoding, scaling, splitting, save/load state
  2. nlp_transformer.py — SimpleTokenizer, TransformerClassifier, NLPTrainer
  3. tflite_inference_api.py — FastAPI app endpoints (mocked TFLite interpreter)
  4. quantize.py    — dynamic_quantize, static_quantize, benchmark_model, compare_models, model_size_kb
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

np    = pytest.importorskip("numpy",  reason="numpy not installed")
import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO    = Path(__file__).parent.parent
_AGENTS  = _REPO / "runtime" / "agents"
for _p in [str(_REPO / "runtime"), str(_AGENTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Optional heavy deps ───────────────────────────────────────────────────────
torch = pytest.importorskip("torch", reason="torch not installed")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_csv(tmp_path: Path, rows: int = 100) -> Path:
    """Create a minimal CSV dataset with numeric + categorical features and a label."""
    import pandas as pd

    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "feat_num_1": rng.standard_normal(rows),
        "feat_num_2": rng.uniform(0, 10, rows),
        "feat_cat":   np.where(rng.random(rows) > 0.5, "cat_A", "cat_B"),
        "label":      np.where(rng.random(rows) > 0.5, "positive", "negative"),
    })
    # Introduce a few missing values
    df.loc[0, "feat_num_1"] = float("nan")
    df.loc[1, "feat_cat"] = None
    p = tmp_path / "raw.csv"
    df.to_csv(p, index=False)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. DataPrep
# ─────────────────────────────────────────────────────────────────────────────

pandas = pytest.importorskip("pandas", reason="pandas not installed")


class TestDataPrep:
    from neural_network.data_prep import DataPrep

    def test_fit_transform_returns_three_splits(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label", val_ratio=0.1, test_ratio=0.1, seed=0)
        train, val, test = prep.fit_transform(str(csv))

        # Each split is (X, y)
        for split in (train, val, test):
            assert len(split) == 2
            X, y = split
            assert X.ndim == 2
            assert y.ndim == 1
            assert X.dtype == np.float32
            assert y.dtype == np.int64

    def test_split_sizes_sum_to_total(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path, rows=200)
        prep = DataPrep(target_column="label", val_ratio=0.1, test_ratio=0.1, seed=0)
        (X_tr, y_tr), (X_v, y_v), (X_te, y_te) = prep.fit_transform(str(csv))
        total = len(X_tr) + len(X_v) + len(X_te)
        assert total == 200

    def test_label_vocab_populated(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label")
        prep.fit_transform(str(csv))
        assert "positive" in prep._label_vocab
        assert "negative" in prep._label_vocab
        assert len(prep._label_vocab) == 2

    def test_save_creates_prep_state_json(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label")
        prep.fit_transform(str(csv))
        out_dir = tmp_path / "processed"
        prep.save(str(out_dir))
        assert (out_dir / "prep_state.json").exists()

    def test_save_splits_creates_npz(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label")
        train, val, test = prep.fit_transform(str(csv))
        out_dir = tmp_path / "processed"
        prep.save_splits(str(out_dir), train, val, test)
        for name in ("train", "val", "test"):
            assert (out_dir / f"{name}.npz").exists()

    def test_missing_target_column_raises(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="nonexistent_column")
        with pytest.raises(ValueError, match="nonexistent_column"):
            prep.fit_transform(str(csv))

    def test_minmax_scaling(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label", scaling="minmax")
        (X, _), _, _ = prep.fit_transform(str(csv))
        # After minmax scaling numeric values should be in [0, 1] (approximately)
        assert np.all(X >= -1e-6)
        assert np.all(X <= 1.0 + 1e-6)

    def test_no_scaling(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep_none = DataPrep(target_column="label", scaling="none")
        prep_std  = DataPrep(target_column="label", scaling="standard")
        (X_none, _), _, _ = prep_none.fit_transform(str(csv))
        (X_std,  _), _, _ = prep_std.fit_transform(str(csv))
        assert not np.allclose(X_none, X_std)

    def test_save_before_fit_raises(self, tmp_path):
        from neural_network.data_prep import DataPrep

        prep = DataPrep(target_column="label")
        with pytest.raises(RuntimeError, match="fit_transform"):
            prep.save(str(tmp_path / "out"))

    def test_ohe_produces_binary_columns(self, tmp_path):
        from neural_network.data_prep import DataPrep

        csv = _make_csv(tmp_path)
        prep = DataPrep(target_column="label", scaling="none")
        (X, _), _, _ = prep.fit_transform(str(csv))
        # OHE columns should contain only 0.0 or 1.0
        ohe_start = sum(1 for c in prep._feature_columns if "__" not in c)
        ohe_block = X[:, ohe_start:]
        unique_vals = set(np.unique(ohe_block))
        assert unique_vals.issubset({0.0, 1.0})


# ─────────────────────────────────────────────────────────────────────────────
# 2. NLP Transformer
# ─────────────────────────────────────────────────────────────────────────────

class TestSimpleTokenizer:
    def test_fit_builds_vocab(self):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=100, max_len=16)
        texts = ["hello world", "hello python", "world is great"]
        tok.fit(texts)
        assert tok.vocab_size >= 4  # PAD, UNK + at least some tokens

    def test_encode_length(self):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=100, max_len=8)
        tok.fit(["one two three four five six seven eight nine ten"])
        ids = tok.encode("one two three")
        assert len(ids) == 8  # padded to max_len

    def test_encode_truncation(self):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=200, max_len=4)
        tok.fit(["a b c d e f g"])
        ids = tok.encode("a b c d e f g")
        assert len(ids) == 4

    def test_encode_batch_shape(self):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=100, max_len=10)
        texts = ["hello world", "foo bar baz"]
        tok.fit(texts)
        batch = tok.encode_batch(texts)
        assert batch.shape == (2, 10)
        assert batch.dtype == torch.long

    def test_unknown_token_handled(self):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=10, max_len=5)
        tok.fit(["hello world"])
        ids = tok.encode("unseen_word_xyz")
        # Should not raise; should map to UNK id (1)
        assert 1 in ids

    def test_save_and_load(self, tmp_path):
        from neural_network.nlp_transformer import SimpleTokenizer

        tok = SimpleTokenizer(max_vocab=50, max_len=8)
        tok.fit(["save and load test"])
        path = str(tmp_path / "tokenizer.json")
        tok.save(path)
        tok2 = SimpleTokenizer.load(path)
        assert tok2.vocab_size == tok.vocab_size
        assert tok2.encode("save") == tok.encode("save")


class TestTransformerClassifier:
    @pytest.fixture()
    def small_model(self):
        from neural_network.nlp_transformer import TransformerClassifier

        return TransformerClassifier(
            vocab_size=100,
            num_classes=3,
            d_model=32,
            nhead=4,
            num_layers=1,
            dim_feedforward=64,
            max_len=16,
        )

    def test_forward_output_shape(self, small_model):
        input_ids = torch.randint(0, 100, (4, 16))  # (B=4, L=16)
        logits = small_model(input_ids)
        assert logits.shape == (4, 3)

    def test_predict_returns_valid_class_and_confidence(self, small_model):
        input_ids = torch.randint(0, 100, (2, 16))
        pred, conf = small_model.predict(input_ids)
        assert pred.shape == (2,)
        assert conf.shape == (2,)
        assert all(0 <= int(p) < 3 for p in pred.tolist())
        assert all(0.0 <= float(c) <= 1.0 for c in conf.tolist())

    def test_predict_preserves_eval_mode(self, small_model):
        small_model.eval()
        input_ids = torch.randint(0, 100, (1, 16))
        small_model.predict(input_ids)
        assert not small_model.training

    def test_predict_preserves_train_mode(self, small_model):
        small_model.train()
        input_ids = torch.randint(0, 100, (2, 16))
        small_model.predict(input_ids)
        assert small_model.training

    def test_padding_mask_applied(self, small_model):
        """Batch with all-padding should not raise."""
        input_ids = torch.zeros(2, 16, dtype=torch.long)  # all PAD
        # Should not raise even if everything is masked
        logits = small_model(input_ids)
        assert logits.shape == (2, 3)


class TestNLPTrainer:
    @pytest.fixture()
    def trainer_and_data(self):
        from neural_network.nlp_transformer import SimpleTokenizer, TransformerClassifier, NLPTrainer

        texts = [f"sample text number {i} with some words here" for i in range(40)]
        labels = [i % 2 for i in range(40)]

        tok = SimpleTokenizer(max_vocab=50, max_len=10)
        tok.fit(texts)

        model = TransformerClassifier(
            vocab_size=tok.vocab_size,
            num_classes=2,
            d_model=16,
            nhead=2,
            num_layers=1,
            dim_feedforward=32,
            max_len=10,
        )

        trainer = NLPTrainer(model, tok, lr=1e-3, batch_size=8, device="cpu")
        return trainer, texts, labels

    def test_train_returns_history(self, trainer_and_data):
        trainer, texts, labels = trainer_and_data
        history = trainer.train(texts, labels, epochs=2)
        assert len(history) == 2
        assert "train_loss" in history[0]
        assert "train_acc" in history[0]

    def test_train_with_validation(self, trainer_and_data):
        trainer, texts, labels = trainer_and_data
        val_texts = texts[:10]
        val_labels = labels[:10]
        history = trainer.train(texts, labels, val_texts, val_labels, epochs=1)
        assert "val_loss" in history[0]
        assert "val_acc" in history[0]

    def test_evaluate_returns_loss_and_acc(self, trainer_and_data):
        trainer, texts, labels = trainer_and_data
        result = trainer.evaluate(texts[:10], labels[:10])
        assert "loss" in result
        assert "accuracy" in result
        assert 0.0 <= result["accuracy"] <= 1.0

    def test_save_and_load(self, trainer_and_data, tmp_path):
        trainer, texts, labels = trainer_and_data
        trainer.train(texts, labels, epochs=1)
        path = str(tmp_path / "nlp_model.pth")
        trainer.save(path)
        assert Path(path).exists()
        trainer.load(path)  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# 3. TFLite Inference API
# ─────────────────────────────────────────────────────────────────────────────

class TestTFLiteInferenceAPI:
    """Tests using a mock TFLiteRunner so no actual .tflite file is needed."""

    @pytest.fixture()
    def app(self, monkeypatch):
        """Build the FastAPI app with a mocked TFLiteRunner."""
        from neural_network import tflite_inference_api as api_mod
        from neural_network.tflite_inference_api import TFLiteRunner

        class _MockRunner:
            model_path = "mock_model.tflite"

            @property
            def input_details(self):
                return [{"name": "input", "shape": [-1, 4], "dtype": "float32", "index": 0}]

            @property
            def output_details(self):
                return [{"name": "output", "shape": [-1, 3], "dtype": "float32", "index": 0}]

            def run(self, inputs: np.ndarray) -> np.ndarray:
                batch = inputs.shape[0]
                # Fake 3-class logits
                return np.random.default_rng(42).standard_normal((batch, 3)).astype(np.float32)

            def predict_proba(self, inputs: np.ndarray) -> np.ndarray:
                raw = self.run(inputs)
                exp = np.exp(raw - raw.max(axis=1, keepdims=True))
                return exp / exp.sum(axis=1, keepdims=True)

        # Patch _load_tflite_interpreter to return our mock
        def _mock_load(path):
            return None

        monkeypatch.setattr(api_mod, "_load_tflite_interpreter", _mock_load)

        # Patch TFLiteRunner.__init__ to use mock
        original_init = TFLiteRunner.__init__

        def _mock_init(self, model_path):
            self._interpreter = None
            self._input_details = []
            self._output_details = []
            self.model_path = model_path

        monkeypatch.setattr(TFLiteRunner, "__init__", _mock_init)

        # Replace input/output details properties
        monkeypatch.setattr(TFLiteRunner, "input_details", property(lambda self: _MockRunner().input_details))
        monkeypatch.setattr(TFLiteRunner, "output_details", property(lambda self: _MockRunner().output_details))
        monkeypatch.setattr(TFLiteRunner, "run", lambda self, inputs: _MockRunner().run(inputs))
        monkeypatch.setattr(TFLiteRunner, "predict_proba", lambda self, inputs: _MockRunner().predict_proba(inputs))

        from neural_network.tflite_inference_api import build_app
        return build_app("mock_model.tflite")

    def test_health_returns_ok(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_model_info_returns_metadata(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/model/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "inputs" in data
        assert "outputs" in data

    def test_predict_single_sample(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/predict", json={"inputs": [0.1, 0.2, 0.3, 0.4]})
        assert resp.status_code == 200
        body = resp.json()
        assert "predictions" in body
        assert "latency_ms" in body
        assert isinstance(body["predictions"], list)

    def test_predict_batch(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/predict", json={"inputs": [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["predictions"]) == 2

    def test_predict_with_proba(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/predict", json={"inputs": [[0.1, 0.2, 0.3, 0.4]], "return_proba": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["probabilities"] is not None

    def test_predict_empty_inputs_rejected(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/predict", json={"inputs": []})
        assert resp.status_code == 422

    def test_predict_batch_alias(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/predict/batch", json={"inputs": [[0.1, 0.2, 0.3, 0.4]]})
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. Quantize
# ─────────────────────────────────────────────────────────────────────────────

class TestQuantize:
    @pytest.fixture()
    def small_model(self):
        from neural_network.model import AIEmployeeNet

        model = AIEmployeeNet(input_size=16, hidden_sizes=[32, 16], output_size=4, dropout=0.0)
        model.eval()
        return model

    @pytest.fixture()
    def sample_inputs(self):
        return torch.randn(16, 16)

    def test_dynamic_quantize_returns_model(self, small_model):
        from neural_network.quantize import dynamic_quantize

        q_model = dynamic_quantize(small_model)
        assert q_model is not None

    def test_dynamic_quantize_inference_runs(self, small_model, sample_inputs):
        from neural_network.quantize import dynamic_quantize

        q_model = dynamic_quantize(small_model)
        with torch.no_grad():
            out = q_model(sample_inputs)
        assert out.shape == (16, 4)

    def test_static_quantize_returns_model(self, sample_inputs):
        from neural_network.quantize import static_quantize

        # BatchNorm1d is not supported by PyTorch's QuantizedCPU backend,
        # so use a plain Linear model for static quantization testing.
        class _LinearModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.net = torch.nn.Sequential(
                    torch.nn.Linear(16, 32),
                    torch.nn.ReLU(),
                    torch.nn.Linear(32, 4),
                )
            def forward(self, x):
                return self.net(x)

        model = _LinearModel()
        model.eval()
        q_model = static_quantize(model, sample_inputs, backend="qnnpack")
        assert q_model is not None
        with torch.no_grad():
            out = q_model(sample_inputs)
        assert out.shape == (16, 4)

    def test_benchmark_returns_expected_keys(self, small_model, sample_inputs):
        from neural_network.quantize import benchmark_model

        results = benchmark_model(small_model, sample_inputs, n_runs=10)
        for key in ("mean_ms", "std_ms", "min_ms", "max_ms", "throughput_samples_per_sec", "batch_size"):
            assert key in results

    def test_benchmark_mean_ms_positive(self, small_model, sample_inputs):
        from neural_network.quantize import benchmark_model

        results = benchmark_model(small_model, sample_inputs, n_runs=10)
        assert results["mean_ms"] > 0.0

    def test_compare_models_has_speedup(self, small_model, sample_inputs):
        from neural_network.quantize import compare_models, dynamic_quantize

        q_model = dynamic_quantize(small_model)
        comp = compare_models(small_model, q_model, sample_inputs, n_runs=5)
        assert "speedup" in comp
        assert comp["speedup"] > 0.0

    def test_model_size_kb_positive(self, small_model):
        from neural_network.quantize import model_size_kb

        size = model_size_kb(small_model)
        assert size > 0.0

    def test_dynamic_quantize_save_load(self, small_model, sample_inputs, tmp_path):
        from neural_network.quantize import dynamic_quantize

        q_model = dynamic_quantize(small_model)
        # State dict of dynamically quantized models can be saved
        save_path = tmp_path / "q_model.pth"
        torch.save(q_model.state_dict(), str(save_path))
        assert save_path.exists()
