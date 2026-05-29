#!/usr/bin/env python3
"""
Phase 8 — Local helper-model training (numpy-only logistic regression).

Reads a JSON payload from stdin describing the operation, writes a JSON result
to stdout. No heavy ML dependencies: uses the hashing trick + multinomial
logistic regression implemented in numpy (already a project dependency).

Operations:
  - train:    train a classifier on prepared_train.jsonl, write model.json
  - evaluate: score a model.json against prepared_eval.jsonl
  - predict:  classify a single feature dict (advisory inference)

Safety:
  - Only reads/writes paths passed by the trusted Node caller (already
    boundary-checked against FORGE_HOME before invocation).
  - Never installs packages. If numpy is missing, reports NEEDS_SETUP.
"""
import json
import sys
import os
import hashlib


def _fail(msg, code="error"):
    print(json.dumps({"ok": False, "error": msg, "code": code}))
    sys.exit(0)


try:
    import numpy as np
except ImportError:
    _fail("numpy is not installed — run: pip install numpy", code="NEEDS_SETUP")


N_FEATURES = 4096  # hashing-trick dimensionality


def _tokenize(value):
    """Flatten a feature dict/string into bag-of-tokens."""
    tokens = []

    def walk(v, prefix=""):
        if isinstance(v, dict):
            for k, sub in v.items():
                walk(sub, f"{prefix}{k}=")
        elif isinstance(v, list):
            for item in v:
                walk(item, prefix)
        elif v is None:
            tokens.append(f"{prefix}none")
        else:
            s = str(v).lower()
            tokens.append(f"{prefix}{s}")
            # word-level tokens for free-text fields
            for w in s.replace("/", " ").replace("_", " ").replace(".", " ").split():
                if len(w) > 1:
                    tokens.append(f"{prefix}w:{w}")

    walk(value)
    return tokens


def _hash_features(feature_obj):
    vec = np.zeros(N_FEATURES, dtype=np.float64)
    for tok in _tokenize(feature_obj):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % N_FEATURES
        sign = 1.0 if (h // N_FEATURES) % 2 == 0 else -1.0
        vec[idx] += sign
    vec[0] = 1.0  # bias term
    return vec


def _build_matrix(records, label_field="label", input_field="input"):
    X, y_labels = [], []
    for r in records:
        feat = r.get(input_field, r)
        label = r.get(label_field)
        if label is None:
            continue
        X.append(_hash_features(feat))
        y_labels.append(str(label))
    if not X:
        return None, None, None
    classes = sorted(set(y_labels))
    cls_idx = {c: i for i, c in enumerate(classes)}
    y = np.array([cls_idx[l] for l in y_labels], dtype=np.int64)
    return np.array(X), y, classes


def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _train_logreg(X, y, n_classes, epochs=300, lr=0.5, l2=1e-3):
    n_samples, n_feat = X.shape
    W = np.zeros((n_feat, n_classes), dtype=np.float64)
    Y = np.zeros((n_samples, n_classes), dtype=np.float64)
    Y[np.arange(n_samples), y] = 1.0
    for _ in range(epochs):
        probs = _softmax(X @ W)
        grad = X.T @ (probs - Y) / n_samples + l2 * W
        W -= lr * grad
    return W


def _read_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def op_train(payload):
    train_path = payload["train_path"]
    model_path = payload["model_path"]
    label_field = payload.get("label_field", "label")
    input_field = payload.get("input_field", "input")
    epochs = int(payload.get("epochs", 300))

    if not os.path.isfile(train_path):
        _fail(f"train file not found: {train_path}")
    records = _read_jsonl(train_path)
    if len(records) < 2:
        _fail("not enough records to train (need >= 2)", code="too_small")

    X, y, classes = _build_matrix(records, label_field, input_field)
    if X is None:
        _fail("no labeled records found", code="no_labels")
    if len(classes) < 2:
        _fail(f"need >= 2 classes, got {len(classes)}: {classes}", code="single_class")

    W = _train_logreg(X, y, len(classes), epochs=epochs)

    # Training accuracy
    preds = np.argmax(_softmax(X @ W), axis=1)
    train_acc = float((preds == y).mean())

    model = {
        "format": "numpy_logreg_v1",
        "n_features": N_FEATURES,
        "classes": classes,
        "weights": W.tolist(),
        "label_field": label_field,
        "input_field": input_field,
        "train_records": len(records),
        "train_accuracy": train_acc,
    }
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(model, f)
    try:
        os.chmod(model_path, 0o600)
    except OSError:
        pass

    print(json.dumps({
        "ok": True,
        "model_path": model_path,
        "classes": classes,
        "train_records": len(records),
        "train_accuracy": round(train_acc, 4),
    }))


def _load_model(model_path):
    with open(model_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    m["weights"] = np.array(m["weights"], dtype=np.float64)
    return m


def op_evaluate(payload):
    model_path = payload["model_path"]
    eval_path = payload["eval_path"]
    if not os.path.isfile(model_path):
        _fail(f"model not found: {model_path}")
    if not os.path.isfile(eval_path):
        _fail(f"eval file not found: {eval_path}")

    m = _load_model(model_path)
    classes = m["classes"]
    cls_idx = {c: i for i, c in enumerate(classes)}
    records = _read_jsonl(eval_path)
    label_field = m.get("label_field", "label")
    input_field = m.get("input_field", "input")

    correct = 0
    total = 0
    top3_hits = 0
    confusion = {c: {c2: 0 for c2 in classes} for c in classes}
    high_risk_fn = 0   # false negatives on high/critical
    high_risk_total = 0

    for r in records:
        label = r.get(label_field)
        if label is None or str(label) not in cls_idx:
            continue
        total += 1
        feat = r.get(input_field, r)
        probs = _softmax((_hash_features(feat).reshape(1, -1)) @ m["weights"])[0]
        pred_i = int(np.argmax(probs))
        pred = classes[pred_i]
        true = str(label)
        if pred == true:
            correct += 1
        # top-3 recall
        top3 = [classes[i] for i in np.argsort(probs)[::-1][:3]]
        if true in top3:
            top3_hits += 1
        confusion[true][pred] += 1
        # high-risk false-negative tracking (risk classifier)
        if true in ("high", "critical"):
            high_risk_total += 1
            if pred not in ("high", "critical"):
                high_risk_fn += 1

    accuracy = (correct / total) if total else 0.0
    top3_recall = (top3_hits / total) if total else 0.0
    high_risk_fn_rate = (high_risk_fn / high_risk_total) if high_risk_total else 0.0

    print(json.dumps({
        "ok": True,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "top3_recall": round(top3_recall, 4),
            "eval_records": total,
            "high_risk_false_negative_rate": round(high_risk_fn_rate, 4),
            "confusion_matrix": confusion,
            "classes": classes,
        },
    }))


def op_predict(payload):
    model_path = payload["model_path"]
    feature = payload.get("input", {})
    if not os.path.isfile(model_path):
        _fail(f"model not found: {model_path}")
    m = _load_model(model_path)
    probs = _softmax((_hash_features(feature).reshape(1, -1)) @ m["weights"])[0]
    classes = m["classes"]
    ranked = sorted(zip(classes, probs.tolist()), key=lambda x: -x[1])
    print(json.dumps({
        "ok": True,
        "prediction": ranked[0][0],
        "confidence": round(float(ranked[0][1]), 4),
        "ranked": [{"label": c, "prob": round(float(p), 4)} for c, p in ranked],
    }))


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        _fail(f"invalid JSON payload: {e}")
    op = payload.get("operation")
    if op == "train":
        op_train(payload)
    elif op == "evaluate":
        op_evaluate(payload)
    elif op == "predict":
        op_predict(payload)
    else:
        _fail(f"unknown operation: {op}")


if __name__ == "__main__":
    main()
