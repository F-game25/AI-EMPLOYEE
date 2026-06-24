"""G1 — the teammate routes business 'do' requests to the 859-skill catalog
(skills.run) and selects the RIGHT skill, instead of chatting or coincidental
token-overlap with a system capability."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from companion.intent_classifier import get_intent_classifier  # noqa: E402
from companion.execution_broker import _EXACT_TASK_CAPS  # noqa: E402
from skills.catalog import get_skill_catalog  # noqa: E402


def test_business_requests_classify_as_skill_execution():
    ic = get_intent_classifier()
    for text in ["write a blog post about remote work",
                 "find me 50 B2B leads in fintech",
                 "score these leads against our ICP",
                 "draft a cold email to a CFO",
                 "create instagram captions for a launch"]:
        out = ic.classify(text, {})
        assert out["mode"] == "execution", f"{text!r} -> {out['mode']}"
        assert out["task_type"] == "skill", f"{text!r} -> {out['task_type']}"


def test_skill_task_routes_to_skills_run():
    # The broker maps the 'skill' task-type straight to the skill catalog.
    assert _EXACT_TASK_CAPS.get("skill") == "skills.run"


def test_matcher_picks_the_right_executable_skill():
    cat = get_skill_catalog()
    cases = {
        "write a blog post about remote work": "blog_writing",
        "score these leads against our ICP": "qualification_scoring",
        "build a landing page for our app": "landing_page_copy",
        "write a press release for our funding round": "press_releases",
        "generate a youtube script for a demo": "youtube_scripts",
    }
    for goal, expected in cases.items():
        m = cat._match_executable_skillbase(goal)
        assert m is not None, f"no skill matched {goal!r}"
        assert m[0] == expected, f"{goal!r} -> {m[0]} (wanted {expected})"


def test_qa_and_browser_requests_do_not_become_skills():
    ic = get_intent_classifier()
    assert ic.classify("what is a race condition", {})["mode"] == "analysis"
    assert ic.classify("open github.com and screenshot it", {})["task_type"] == "browser"


def test_deep_research_routes_to_real_engine_not_skill():
    ic = get_intent_classifier()
    # "deep research" must hit the multi-hop engine, not a shallow research skill.
    for text in ["do a deep research on the AI note-taking market",
                 "deep dive into fintech lead generation",
                 "research quantum computing in depth"]:
        out = ic.classify(text, {})
        assert out["task_type"] == "research.deep", f"{text!r} -> {out['task_type']}"
    assert _EXACT_TASK_CAPS.get("research.deep") == "research.deep.start"


def test_deep_research_executor_emits_directive_with_clean_topic():
    from companion.execution_broker import ExecutionBroker
    cap = type("C", (), {"subsystem": "research", "id": "research.deep.start"})()
    out = ExecutionBroker._exec_research_deep_start(cap, {"text": "do a deep research on the AI note-taking market"})
    assert out["directive"] == "deep_research"
    assert out["topic"] == "the AI note-taking market"  # command framing stripped
