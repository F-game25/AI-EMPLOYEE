"""Deep research: a run launched with a pre-created report_id must be retrievable
by THAT id (fixes the placeholder-vs-engine id mismatch that made chat/page deep
searches appear to never report back)."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from core import deep_research_engine as dre  # noqa: E402


@pytest.fixture()
def isolated_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(dre, "_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(dre, "_REPORTS_INDEX", tmp_path / "index.json")
    yield


def _stub_engine(engine):
    async def _decompose(topic, depth):
        return ["q1", "q2"]

    async def _discover_all(topic, subqs):
        return [dre.SourceResult(url="https://example.com/a", title="A", snippet="s", sub_question="q1")]

    async def _fetch_all(sources, report):
        for s in sources:
            s.fetched = True
            s.text = "content"
        report.sources_fetched = len(sources)
        return sources

    async def _synthesize_all(topic, subqs, fetched, report):
        return [{"question": "q1", "answer": "ans"}]

    async def _fill_gaps(topic, syntheses, report):
        return []

    async def _generate_report(topic, subqs, fetched, syntheses, report):
        report.executive_summary = "summary"
        report.report_md = "# Report"

    engine._decompose = _decompose
    engine._discover_all = _discover_all
    engine._fetch_all = _fetch_all
    engine._synthesize_all = _synthesize_all
    engine._fill_gaps = _fill_gaps
    engine._generate_report = _generate_report


def test_run_uses_passed_report_id(isolated_reports):
    engine = dre.DeepResearchEngine()
    _stub_engine(engine)
    fixed = "fixedid0000000aa"
    report = asyncio.run(engine.run(topic="quantum widgets", depth="shallow", report_id=fixed))

    # The returned report and the persisted/retrievable report all share the id
    # the caller was handed — so polling /deep/{id} now returns the finished report.
    assert report.id == fixed
    loaded = dre.load_report(fixed)
    assert loaded is not None
    assert loaded["id"] == fixed
    assert loaded["status"] == "done"
    assert loaded["executive_summary"] == "summary"


def test_run_never_fails_terminally_and_is_bounded(isolated_reports, monkeypatch):
    """Pipeline always raises → run() must NOT raise, must NOT loop forever, must
    reiterate a bounded number of times, then deliver a clear partial report."""
    monkeypatch.setattr(dre, "_MAX_RESEARCH_ATTEMPTS", 3)
    q = asyncio.Queue()
    engine = dre.DeepResearchEngine(progress_queue=q)

    calls = {"n": 0}

    async def _always_fail(report, topic, depth):
        calls["n"] += 1
        raise RuntimeError("network down")

    engine._run_pipeline = _always_fail

    report = asyncio.run(engine.run(topic="x", depth="deep", report_id="failid0000000000"))

    # Bounded: pipeline attempted exactly max_attempts times — never infinite.
    assert calls["n"] == 3
    # Never a terminal 'failed' — always delivers a report the user can see.
    assert report.status == "done"
    assert report.partial is True
    assert report.executive_summary  # a clear message informing the user
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    names = [e["event"] for e in events]
    assert names.count("reiterate") == 2  # attempts 2 and 3 are reiterations
    done = [e for e in events if e["event"] == "done"][0]
    assert done["data"].get("partial") is True
    assert "failed" not in names  # never emits a terminal failure


def test_attempts_hard_capped_against_runaway_config(monkeypatch):
    """Even a huge RESEARCH_MAX_ATTEMPTS env can't cause a runaway loop."""
    monkeypatch.setenv("RESEARCH_MAX_ATTEMPTS", "9999")
    import importlib
    importlib.reload(dre)
    try:
        assert dre._MAX_RESEARCH_ATTEMPTS <= dre._RESEARCH_ATTEMPTS_CEILING
    finally:
        monkeypatch.delenv("RESEARCH_MAX_ATTEMPTS", raising=False)
        importlib.reload(dre)


def test_run_without_id_still_generates_one(isolated_reports):
    engine = dre.DeepResearchEngine()
    _stub_engine(engine)
    report = asyncio.run(engine.run(topic="x", depth="shallow"))
    assert report.id and len(report.id) >= 8
    assert dre.load_report(report.id)["status"] == "done"


def test_progress_queue_emits_source_visit_and_done(isolated_reports, monkeypatch):
    q = asyncio.Queue()
    engine = dre.DeepResearchEngine(progress_queue=q)
    _stub_engine(engine)

    # Keep the REAL _fetch_all (which emits source_visit) but mock the network.
    async def _fake_fetch_page(url):
        return {"text": "page content", "error": ""}
    monkeypatch.setattr(dre, "_fetch_page", _fake_fetch_page)
    del engine._fetch_all  # restore the bound class method we stubbed

    asyncio.run(engine.run(topic="x", depth="shallow", report_id="abc12345abc12345"))
    events = []
    while not q.empty():
        events.append(q.get_nowait()["event"])
    assert "started" in events
    assert "source_visit" in events  # sites-visited stream for the chat viz
    assert "done" in events
