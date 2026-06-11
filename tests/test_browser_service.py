"""Tests for the Browser Execution Service (runtime/tools/browser/)."""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME = _ROOT / "runtime"
for _p in (str(_ROOT), str(_RUNTIME)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from tools.browser import browser_service as bs  # noqa: E402
from tools.browser.accessibility_snapshot import snapshot  # noqa: E402
from tools.browser.action_executor import act, resolve_selector  # noqa: E402
from tools.browser.capture import capture  # noqa: E402
from tools.browser.extract import extract  # noqa: E402
from tools.browser.tool_contracts import TOOL_CONTRACTS, check_registry_drift  # noqa: E402

DATA_URL = (
    "data:text/html,<h1>Hello</h1>"
    "<button id=b onclick=\"document.getElementById('out').textContent='clicked'\">Go</button>"
    "<div id=out></div>"
)

_EXE = bs.resolve_executable()
needs_chromium = pytest.mark.skipif(_EXE is None, reason="no chromium bundle found")

_PRIVATE_ALLOWED = os.getenv("URLGUARD_ALLOW_PRIVATE", "").strip().lower() in (
    "1", "true", "yes")


@pytest.fixture(scope="module")
def service():
    svc = bs.get_browser_service()
    yield svc
    svc.close_all()


# ── Executable resolution ──────────────────────────────────────────────────────

def test_resolve_executable():
    exe = bs.resolve_executable()
    if exe is None:
        pytest.skip("no chromium bundle present in repo and no BROWSER_EXECUTABLE")
    assert os.path.isfile(exe) and os.access(exe, os.X_OK)


# ── URL policy (no browser needed) ─────────────────────────────────────────────

def test_check_url_policy():
    assert bs.check_url("data:text/html,<p>x</p>") is None
    assert bs.check_url("about:blank") is None
    assert bs.check_url("") is not None
    assert bs.check_url("javascript:alert(1)") is not None
    if os.getenv("BROWSER_ALLOW_FILE_URLS", "").strip().lower() not in ("1", "true", "yes"):
        assert bs.check_url("file:///etc/passwd") is not None
    if not _PRIVATE_ALLOWED:
        # SSRF: loopback + cloud metadata blocked via core.url_guard
        assert bs.check_url("http://127.0.0.1:1/") is not None
        assert bs.check_url("http://169.254.169.254/latest/meta-data") is not None


def test_ref_selector_resolution():
    assert resolve_selector("@e3") == '[data-ai-ref="e3"]'
    assert resolve_selector("e12") == '[data-ai-ref="e12"]'
    assert resolve_selector("#out") == "#out"


# ── Live roundtrip ─────────────────────────────────────────────────────────────

@needs_chromium
def test_roundtrip_open_snapshot_extract_capture_act(service):
    opened = service.open(DATA_URL)
    assert opened["session_id"].startswith("bs-")
    sess = service.get_session(opened["session_id"])
    assert sess is not None
    try:
        # snapshot: button is tagged with a stable ref
        snap = snapshot(sess)
        assert snap["ref_count"] >= 1 and snap["tree"] is not None
        buttons = [r for r in snap["refs"] if r["role"] == "button"]
        assert buttons, f"no button ref found in {snap['refs']}"
        ref = buttons[0]["ref"]
        assert ref.startswith("e")

        # extract: page text contains the heading
        text = extract(sess, "text")
        assert text["ok"] and "Hello" in text["data"]

        # capture: real PNG on disk
        shot = capture(sess, "screenshot")
        assert shot["ok"], shot
        png = Path(shot["path"])
        assert png.is_file() and png.read_bytes()[:4] == b"\x89PNG"

        # act: click via the ref flips #out (approval is a capability-layer
        # concern — the executor is exercised directly)
        result = act(sess, "click", f"@{ref}")
        assert result["ok"], result
        assert result["side_effect_class"] in ("navigation", "submit")
        out = extract(sess, "text", "#out")
        assert out["ok"] and out["data"].strip() == "clicked"
    finally:
        service.close(opened["session_id"])


@needs_chromium
def test_ref_stability_across_mutation(service):
    opened = service.open(DATA_URL)
    sess = service.get_session(opened["session_id"])
    try:
        first = snapshot(sess)
        button_ref = next(r["ref"] for r in first["refs"] if r["role"] == "button")
        # mutate the page, then re-snapshot
        sess.call(lambda: sess.page.evaluate(
            "() => { const b = document.createElement('button');"
            " b.textContent = 'New'; document.body.appendChild(b); }"))
        second = snapshot(sess)
        same = next(r["ref"] for r in second["refs"]
                    if r["role"] == "button" and r["name"] == "Go")
        assert same == button_ref, "existing element's ref must survive mutation"
        assert second["ref_count"] == first["ref_count"] + 1
    finally:
        service.close(opened["session_id"])


@needs_chromium
def test_session_isolation_and_close_all(service):
    a = service.open(DATA_URL)
    b = service.open(DATA_URL)
    assert a["session_id"] != b["session_id"]
    assert service.get_session(a["session_id"]) is not None
    assert service.get_session(b["session_id"]) is not None
    out = service.close_all()
    assert out["closed"] >= 2
    assert service.get_session(a["session_id"]) is None
    assert service.list_sessions() == []


# ── Companion integration ──────────────────────────────────────────────────────

def test_broker_open_refuses_private_url_without_throwing():
    if _PRIVATE_ALLOWED:
        pytest.skip("URLGUARD_ALLOW_PRIVATE set — refusal path disabled")
    from companion.capability_registry import get_capability_registry
    from companion.execution_broker import get_execution_broker
    broker = get_execution_broker()
    cap = get_capability_registry().get("browser.open")
    assert cap is not None
    out = broker._dispatch["browser.open"](cap, {"url": "http://127.0.0.1:1"})
    assert out["status"] == "refused"
    assert "note" in out


def test_registry_browser_act_is_gated():
    from companion.capability_registry import get_capability_registry
    from companion.schemas import L3
    cap = get_capability_registry().get("browser.act")
    assert cap is not None
    assert cap.risk_level == L3
    assert cap.requires_approval is True
    assert "interacts with external website" in cap.side_effects


def test_broker_dispatch_wiring():
    from companion.execution_broker import get_execution_broker
    dispatch = get_execution_broker()._dispatch
    for cap_id in ("browser.open", "browser.snapshot", "browser.extract",
                   "browser.capture", "browser.close"):
        assert cap_id in dispatch, f"{cap_id} missing from broker dispatch"
    assert "browser.act" not in dispatch, \
        "browser.act must NEVER auto-run from the broker (approval-gated L3)"


def test_tool_contracts_match_registry():
    assert set(TOOL_CONTRACTS) == {
        "browser.open", "browser.snapshot", "browser.extract",
        "browser.capture", "browser.close", "browser.act"}
    problems = check_registry_drift()
    assert problems == [], f"contracts/registry drift: {problems}"
