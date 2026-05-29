"""
Phase 8 — Local Model Training Pipeline Tests

Covers: dataset validation, secret detection, invalid jsonl rejection,
path traversal rejection, too-small dataset block, failed-runs-not-positive,
eval gate logic, numpy trainer, router safety invariant, route auth (skipped
without live server).
"""
import json
import os
import subprocess
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN_SVC = os.path.join(REPO_ROOT, 'backend', 'services', 'forge_training.js')
TRAIN_PY = os.path.join(REPO_ROOT, 'backend', 'forge_train.py')
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8787")
TIMEOUT = 10


def node_eval(snippet: str, timeout: int = 15) -> dict:
    svc = TRAIN_SVC.replace("\\", "/")
    script = f"""
const svc = require({json.dumps(svc)});
(async () => {{
  try {{
    const result = await Promise.resolve(({snippet}));
    console.log(JSON.stringify({{ ok: true, result }}));
  }} catch(e) {{
    console.log(JSON.stringify({{ ok: false, error: e.message }}));
  }}
}})();
"""
    proc = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT)
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError(f"no node output: {proc.stderr[:400]}")
    return json.loads([l for l in out.split('\n') if l.strip()][-1])


def py_train(payload: dict, timeout: int = 30) -> dict:
    proc = subprocess.run(['python3', TRAIN_PY], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=timeout)
    out = proc.stdout.strip()
    return json.loads([l for l in out.split('\n') if l.strip()][-1])


class TestSecretDetection:
    def _check(self, line):
        r = node_eval(f"svc.lineContainsSecret({json.dumps(line)})")
        assert r['ok'], r.get('error')
        return r['result']

    def test_detects_jwt(self):
        assert self._check("data eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijklmnop is here") is True

    def test_detects_anthropic_key(self):
        assert self._check("key sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV1234 here") is True

    def test_detects_aws_key(self):
        assert self._check("AKIAIOSFODNN7EXAMPLE") is True

    def test_detects_private_key(self):
        assert self._check("-----BEGIN RSA PRIVATE KEY-----") is True

    def test_clean_line_passes(self):
        assert self._check('{"goal": "add tests", "label": "low"}') is False


class TestPathSafety:
    def test_training_dir_inside_forge_home(self):
        tmp = tempfile.mkdtemp()
        r = node_eval(f"svc.trainingDir({json.dumps(tmp)}, 'proj1', 'trn-abc')")
        assert r['ok'], r.get('error')
        assert tmp in r['result'] and 'proj1' in r['result']

    def test_assert_inside_rejects_absolute_escape(self):
        tmp = tempfile.mkdtemp()
        r = node_eval(f"svc.assertInsideForgeHome('/etc/passwd', {json.dumps(tmp)})")
        assert r['ok'] is False

    def test_assert_inside_accepts_valid(self):
        tmp = tempfile.mkdtemp()
        inner = os.path.join(tmp, 'training', 'p', 'model.json')
        r = node_eval(f"svc.assertInsideForgeHome({json.dumps(inner)}, {json.dumps(tmp)})")
        assert r['ok'], r.get('error')


class TestDatasetValidation:
    def _write(self, lines, forge_home, project='p1'):
        d = os.path.join(forge_home, 'learning', project)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'ds.jsonl')
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        return path

    def _validate(self, dataset, model_type, forge_home, options=None):
        r = node_eval(f"svc.validateTrainingDataset({json.dumps(dataset)}, {json.dumps(model_type)}, {json.dumps(options or {})}, {json.dumps(forge_home)})")
        assert r['ok'], r.get('error')
        return r['result']

    def _risk(self, risk, goal="do x", fp="src/a.py"):
        return json.dumps({"eval_type": "risk_classifier_eval", "input": {"goal": goal, "file_path": fp, "action_type": "update", "stack": "python"}, "expected": {"classification": risk}, "confidence": "medium"})

    def test_validates_good_dataset(self):
        tmp = tempfile.mkdtemp()
        lines = []
        for i in range(15):
            lines.append(self._risk("low", f"add test {i}", f"tests/t{i}.py"))
            lines.append(self._risk("critical", f"delete db {i}", f"db/d{i}.sql"))
        ds = {"dataset_id": "d1", "export_path": self._write(lines, tmp)}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['secret_scan_passed'] is True
        assert res['approved_count'] >= 20
        assert res['result'] in ('warn', 'passed') and res['ok'] is True

    def test_rejects_secret(self):
        tmp = tempfile.mkdtemp()
        lines = [self._risk("low") for _ in range(10)]
        lines.append('{"eval_type":"risk_classifier_eval","input":{"goal":"sk-ant-api03-ABCDEFGHIJKLMNOP1234567"},"expected":{"classification":"low"}}')
        ds = {"dataset_id": "d1", "export_path": self._write(lines, tmp)}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['secret_scan_passed'] is False and res['result'] == 'failed' and res['ok'] is False

    def test_rejects_invalid_jsonl(self):
        tmp = tempfile.mkdtemp()
        ds = {"dataset_id": "d1", "export_path": self._write(["{not json", "bad}"], tmp)}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['result'] == 'failed'
        assert any('JSON' in i for i in res['issues'])

    def test_rejects_path_outside_forge_home(self):
        tmp = tempfile.mkdtemp()
        ds = {"dataset_id": "d1", "export_path": "/etc/passwd"}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['ok'] is False and res['result'] == 'failed'
        assert any('boundary' in i.lower() for i in res['issues'])

    def test_too_small_blocked(self):
        tmp = tempfile.mkdtemp()
        ds = {"dataset_id": "d1", "export_path": self._write([self._risk("low"), self._risk("critical")], tmp)}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['result'] == 'too_small' and res['ok'] is False

    def test_single_class_rejected(self):
        tmp = tempfile.mkdtemp()
        ds = {"dataset_id": "d1", "export_path": self._write([self._risk("low") for _ in range(40)], tmp)}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['result'] in ('too_small', 'failed')
        assert any('class' in i.lower() for i in res['issues'])

    def test_missing_file_rejected(self):
        tmp = tempfile.mkdtemp()
        ds = {"dataset_id": "d1", "export_path": os.path.join(tmp, "learning", "p1", "nope.jsonl")}
        res = self._validate(ds, "risk_classifier", tmp)
        assert res['ok'] is False and res['result'] == 'failed'


class TestEvaluationGate:
    def _gate(self, model_type, metrics, baseline=0):
        r = node_eval(f"svc.applyEvalGate({json.dumps(model_type)}, {json.dumps(metrics)}, {baseline})")
        assert r['ok'], r.get('error')
        return r['result']

    def test_good_model_passes(self):
        assert self._gate("risk_classifier", {"accuracy": 0.85, "high_risk_false_negative_rate": 0.1})['passed'] is True

    def test_low_accuracy_blocked(self):
        res = self._gate("risk_classifier", {"accuracy": 0.4, "high_risk_false_negative_rate": 0.1})
        assert res['passed'] is False and any('accuracy' in r for r in res['failure_reasons'])

    def test_high_risk_fn_blocked(self):
        res = self._gate("risk_classifier", {"accuracy": 0.9, "high_risk_false_negative_rate": 0.5})
        assert res['passed'] is False
        assert any('false-negative' in r or 'unsafe' in r for r in res['failure_reasons'])

    def test_must_beat_baseline(self):
        res = self._gate("skill_selector", {"accuracy": 0.5}, baseline=0.6)
        assert res['passed'] is False and any('baseline' in r for r in res['failure_reasons'])


class TestNumpyTrainer:
    def _make_data(self):
        tmp = tempfile.mkdtemp()
        train = os.path.join(tmp, 'train.jsonl')
        ex = [
            {"input": {"goal": "add tests", "file_path": "tests/x.py", "action_type": "create"}, "label": "low"},
            {"input": {"goal": "delete db", "file_path": "db/s.sql", "action_type": "delete"}, "label": "critical"},
            {"input": {"goal": "update docs", "file_path": "README.md", "action_type": "update"}, "label": "low"},
            {"input": {"goal": "edit auth", "file_path": "auth/mw.js", "action_type": "update"}, "label": "high"},
            {"input": {"goal": "add log", "file_path": "log.js", "action_type": "create"}, "label": "low"},
            {"input": {"goal": "drop table", "file_path": "migrate/drop.sql", "action_type": "delete"}, "label": "critical"},
            {"input": {"goal": "edit payment", "file_path": "pay/charge.js", "action_type": "update"}, "label": "high"},
            {"input": {"goal": "fix typo", "file_path": "docs/i.md", "action_type": "update"}, "label": "low"},
        ]
        with open(train, 'w') as f:
            f.write('\n'.join(json.dumps(e) for e in ex))
        return tmp, train

    def test_train_produces_model(self):
        tmp, train = self._make_data()
        model = os.path.join(tmp, 'model.json')
        r = py_train({"operation": "train", "train_path": train, "model_path": model})
        assert r['ok'], r.get('error')
        assert os.path.isfile(model)
        assert set(r['classes']) == {'low', 'high', 'critical'}
        assert r['train_accuracy'] >= 0.7

    def test_evaluate_returns_metrics(self):
        tmp, train = self._make_data()
        model = os.path.join(tmp, 'model.json')
        py_train({"operation": "train", "train_path": train, "model_path": model})
        r = py_train({"operation": "evaluate", "model_path": model, "eval_path": train})
        assert r['ok'], r.get('error')
        for k in ('accuracy', 'high_risk_false_negative_rate', 'confusion_matrix'):
            assert k in r['metrics']

    def test_predict_classifies_high_risk(self):
        tmp, train = self._make_data()
        model = os.path.join(tmp, 'model.json')
        py_train({"operation": "train", "train_path": train, "model_path": model})
        r = py_train({"operation": "predict", "model_path": model,
                      "input": {"goal": "wipe all production data", "file_path": "db/wipe.sql", "action_type": "delete"}})
        assert r['ok'], r.get('error')
        assert r['prediction'] in ('critical', 'high')

    def test_train_rejects_single_class(self):
        tmp = tempfile.mkdtemp()
        train = os.path.join(tmp, 'train.jsonl')
        with open(train, 'w') as f:
            f.write('\n'.join(json.dumps({"input": {"x": i}, "label": "low"}) for i in range(5)))
        r = py_train({"operation": "train", "train_path": train, "model_path": os.path.join(tmp, 'm.json')})
        assert r['ok'] is False and r.get('code') == 'single_class'

    def test_train_rejects_too_few(self):
        tmp = tempfile.mkdtemp()
        train = os.path.join(tmp, 'train.jsonl')
        with open(train, 'w') as f:
            f.write(json.dumps({"input": {"x": 1}, "label": "low"}))
        r = py_train({"operation": "train", "train_path": train, "model_path": os.path.join(tmp, 'm.json')})
        assert r['ok'] is False


class TestNoPositiveFromFailures:
    def test_failed_run_cases_use_negative_labels(self):
        tmp = tempfile.mkdtemp()
        d = os.path.join(tmp, 'learning', 'p1')
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'ds.jsonl')
        lines = []
        for i in range(15):
            lines.append(json.dumps({"eval_type": "planner_eval", "input": {"goal": f"huge refactor {i}", "stack": "python"}, "expected": {"risk_level": "dangerous", "should_decompose": True}, "confidence": "low"}))
            lines.append(json.dumps({"eval_type": "planner_eval", "input": {"goal": f"small fix {i}", "stack": "python"}, "expected": {"risk_level": "safe", "should_decompose": False}, "confidence": "medium"}))
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        ds = {"dataset_id": "d1", "export_path": path}
        r = node_eval(f"svc.validateTrainingDataset({json.dumps(ds)}, 'decomposer_helper', {{}}, {json.dumps(tmp)})")
        assert r['ok'], r.get('error')
        labels = set(r['result'].get('class_distribution', {}).keys())
        assert labels.issubset({'decompose', 'single_run'})
        assert 'decompose' in labels  # failed runs → negative "decompose" label


@pytest.mark.skipif(os.environ.get("SKIP_LIVE_TESTS", "1") == "1", reason="Live server tests skipped")
class TestTrainingAPIRoutes:
    def test_training_overview_requires_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/training", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_create_run_requires_auth(self):
        import requests
        r = requests.post(f"{BASE_URL}/api/forge/projects/fake/training-runs", json={"model_type": "risk_classifier"}, timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_model_versions_requires_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/model-versions", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_promote_requires_auth(self):
        import requests
        r = requests.post(f"{BASE_URL}/api/forge/model-versions/fake/promote", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_rollback_requires_auth(self):
        import requests
        r = requests.post(f"{BASE_URL}/api/forge/model-versions/fake/rollback", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_invalid_model_type_rejected(self):
        import requests
        token = os.environ.get("TEST_JWT", "")
        r = requests.post(f"{BASE_URL}/api/forge/projects/test/training-runs", json={"model_type": "full_code_model"}, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
        assert r.status_code in (400, 401, 403, 404)


class TestRouterSafetyInvariant:
    """Static check: helper models are advisory and never wired into classifyCommand."""

    def test_helper_advise_marked_advisory(self):
        src = open(os.path.join(REPO_ROOT, 'backend', 'routes', 'forge.js')).read()
        assert 'advisory: true' in src
        assert 'helperModelAdvise' in src
        idx = src.find('function classifyCommand')
        end = src.find('\n  }', idx)
        body = src[idx:end]
        assert 'helperModelAdvise' not in body
        assert 'model_version' not in body

    def test_command_blocked_patterns_exist(self):
        src = open(os.path.join(REPO_ROOT, 'backend', 'routes', 'forge.js')).read()
        assert 'CMD_BLOCKED' in src and "level: 'BLOCKED'" in src


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
